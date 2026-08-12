"""A controllable TCP link between the browser and classroom-core.

The UI is pointed at this port instead of core's, so a test can do to the
connection what no code change can fake:

* `cut()`      — close every live connection and refuse new ones. A pulled
                 cable, an AP that went down, a laptop lid.
* `blackhole()`— accept the connection and then say nothing, ever. This is the
                 nastier and more realistic failure: TCP still completes the
                 handshake, so the client believes it is connected and can hang
                 indefinitely. I9 is only meaningful against this mode.
* `restore()`  — plug it back in.

Raw TCP, so it is transparent to HTTP, WebSocket upgrades and everything else.
Runs on its own event loop in a background thread, which keeps it independent
of pytest-asyncio's loop scoping.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from .net import free_port

MODE_PASS = "pass"
MODE_CUT = "cut"
MODE_BLACKHOLE = "blackhole"


class TcpProxy:
    def __init__(self, target_port: int, listen_port: int | None = None) -> None:
        self.target_port = target_port
        self.port = listen_port or free_port()
        #: A tiny HTTP control surface, so a browser scenario can pull the
        #: cable itself instead of needing pytest to do it mid-run.
        self.control_port = free_port({self.port})
        self.mode = MODE_PASS
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: asyncio.AbstractServer | None = None
        self._control: asyncio.AbstractServer | None = None
        self._conns: set[Any] = set()
        self._ready = threading.Event()

    @property
    def control_url(self) -> str:
        return f"http://127.0.0.1:{self.control_port}"

    # ------------------------------------------------------------- lifecycle

    def start(self) -> "TcpProxy":
        self._thread = threading.Thread(target=self._run, name="tcp-proxy", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("tcp proxy failed to start")
        return self

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())
        self._loop.run_forever()

    async def _serve(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)
        self._control = await asyncio.start_server(
            self._handle_control, "127.0.0.1", self.control_port
        )
        self._ready.set()

    async def _handle_control(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            path = line.decode("latin-1").split(" ")[1] if b" " in line else "/"
            action = path.strip("/").split("?")[0]
            if action == "cut":
                self.mode = MODE_CUT
                await self._drop_all()
            elif action == "blackhole":
                self.mode = MODE_BLACKHOLE  # existing sockets stay open, and silent
            elif action == "restore":
                self.mode = MODE_PASS
            body = f'{{"mode":"{self.mode}"}}'.encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
                b"access-control-allow-origin: *\r\n"
                + f"content-length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    # --------------------------------------------------------------- control

    def _submit(self, coro) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=10)

    def cut(self) -> None:
        self.mode = MODE_CUT
        self._submit(self._drop_all())

    def blackhole(self) -> None:
        """Bytes stop; nothing closes.

        Existing connections are deliberately **not** dropped. Closing them
        would make this the same test as `cut()`, and the whole point of a
        black hole is that the socket still looks alive: no FIN, no RST, no
        error event. That is the failure a client with no liveness check
        cannot see.
        """
        self.mode = MODE_BLACKHOLE

    def restore(self) -> None:
        self.mode = MODE_PASS

    async def _drop_all(self) -> None:
        for writer in list(self._conns):
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
        self._conns.clear()

    # --------------------------------------------------------------- forward

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.mode == MODE_CUT:
            writer.close()
            return
        if self.mode == MODE_BLACKHOLE:
            # Accepted, never answered. The client's connect() succeeded.
            self._conns.add(writer)
            try:
                while self.mode == MODE_BLACKHOLE:
                    await asyncio.sleep(0.2)
            finally:
                self._conns.discard(writer)
                try:
                    writer.close()
                except Exception:  # noqa: BLE001
                    pass
            return

        try:
            up_r, up_w = await asyncio.open_connection("127.0.0.1", self.target_port)
        except OSError:
            writer.close()
            return

        self._conns.add(writer)
        self._conns.add(up_w)

        async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    if self.mode == MODE_BLACKHOLE:
                        # Read it and throw it away, like a router that stopped
                        # forwarding. Neither end is told anything.
                        continue
                    dst.write(data)
                    await dst.drain()
            except (OSError, asyncio.CancelledError, ConnectionError):
                pass
            finally:
                try:
                    dst.close()
                except Exception:  # noqa: BLE001
                    pass

        try:
            await asyncio.gather(pump(reader, up_w), pump(up_r, writer))
        finally:
            self._conns.discard(writer)
            self._conns.discard(up_w)
