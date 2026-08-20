/**
 * What the room says to the class, in the deployment's own languages.
 *
 * NS-7: software never names a language. These strings are Vietnamese because
 * the first deployment is a Vietnamese classroom in Hà Giang — **not** because
 * the code knows what Vietnamese is. A school in Laos replaces this one file
 * and touches nothing else; no logic reads, parses or branches on the text.
 *
 * The proper end state is for a deployment to declare these next to its
 * languages, timetable and roster, and for Core to serve them. This file is the
 * single seam that makes that a later refactor instead of a hunt through the
 * source. Everything child-facing lives here; nothing child-facing lives
 * anywhere else.
 */
export interface RoomLabel {
  /** Read from the back of the room. The class's own language. */
  cta: string
  /** The quieter line under it, in the language being taught. */
  sub: string
}

export const ROOM_LABELS = {
  speaking: { cta: 'Cô đang nói', sub: 'Listen' },
  hearing: { cta: 'Cô đang nghe con', sub: "I'm listening" },
  thinking: { cta: 'Cô đang nghĩ', sub: 'One moment' },
  listening: { cta: 'Tới lượt con nói', sub: 'Your turn — just speak' },
  deaf: { cta: 'Cô chưa nghe được', sub: 'The room cannot hear — check the microphone' },
  fault: { cta: 'Cô đang kiểm tra lớp', sub: 'She will start again herself' },
  waking: { cta: 'Cô đang tới bảng', sub: '' },
  comingReady: { cta: 'Cô sắp bắt đầu', sub: 'She opens the class herself' },
  comingWaiting: { cta: 'Đang chuẩn bị lớp', sub: 'Waiting for the teacher' },
  /**
   * Something on the board did not render. The class sees this, so it says
   * nothing about protocols, versions or JSON -- a child cannot act on any of
   * that, and neither can the adult in the room. The detail goes to the
   * console and to /teacher/status, where someone who can act on it will look.
   */
  boardFault: { cta: 'Bảng đang trục trặc một chút', sub: 'She keeps teaching — the board will come back' },
} as const satisfies Record<string, RoomLabel>

/** The short lead-in on the heard-echo chip -- "You said:", in the class's own language. */
export const HEARD_PREFIX = 'Con nói:'

/**
 * The student camera corner. Perception ships (`services/vision`, and
 * `docs/decisions/2026-08-20-the-room-knows-who.md`), so "recognised" is a real
 * state now — but the others still are too: hardware missing, hardware present
 * but not streaming, a live self-view. No state here fabricates a video feed or
 * a recognised child, and the corner never shows a similarity score.
 */
export const CAMERA_LABELS = {
  noCamera: { cta: 'Không có camera', sub: 'No camera' },
  off: { cta: 'Camera đang tắt', sub: 'Camera is off' },
  requesting: { cta: 'Đang bật camera…', sub: 'Turning on…' },
  live: { cta: 'Con có thể thấy mình', sub: 'You can see yourself' },
  /** `name` is a first name only — the same bar StudentName already shows. */
  recognised: (name: string) => ({ cta: `Cô nhận ra: ${name}`, sub: `Recognised: ${name}` }),
} as const

/** Microphone faults. Shown to the adult who can act on them, on a projector. */
export const MIC_LABELS = {
  insecure:
    'Trình duyệt này không ghi âm được ở đây — cần https:// hoặc localhost. '
    + '(This browser cannot record audio here.)',
  blocked:
    'Micro đang bị chặn. Cho phép micro cho trang này trên thanh địa chỉ rồi thử lại. '
    + '(The microphone is blocked.)',
  missing:
    'Không tìm thấy micro. Kiểm tra đã cắm chưa, và không có ứng dụng nào đang giữ nó. '
    + '(No microphone was available.)',
} as const

/**
 * The front door — `/`, the page before the room.
 *
 * Same rule as everything else in this file: these strings are the class's own
 * language because the first deployment is a Vietnamese school, not because any
 * code here knows what Vietnamese is.
 */
export const LOBBY_LABELS = {
  title: 'Lớp tiếng Anh của con',
  subtitle: 'Chọn bài học hôm nay',
  /** Under a card the child has already been taught. */
  done: 'Đã học',
  /** The one card that is pressable. */
  next: 'Học tiếp',
  /** Not yet — the period before it has not been held. */
  locked: 'Chưa mở',
  /** The room is not ready to be entered yet. */
  warming: 'Đang chuẩn bị lớp…',
  ready: 'Lớp đã sẵn sàng',
  /** Something below the room is down; an adult has to look. */
  down: 'Lớp chưa mở được — nhờ thầy cô kiểm tra giúp',
  /** Shown while the browser navigates and she starts the class. */
  entering: 'Đang vào lớp…',
  /** The count under the header. */
  heldCount: (n: number) => (n === 0 ? 'Con chưa học buổi nào' : `Con đã học ${n} buổi`),
  /** What this period will teach, from the unit map's own words. */
  inPlay: 'Hôm nay học:',

  // ---- the camera at the door -------------------------------------------
  /** Before any face has been resolved. */
  looking: 'Cô đang nhìn xem ai đây…',
  /** A child the room already knows. */
  hello: (name: string) => `Chào con, ${name}!`,
  /** Nobody enrolled matches. Never phrased as a failure. */
  stranger: 'Cô chưa biết con là ai',
  /** Opens the enrolment form. */
  imNew: 'Con là bạn mới',
  /** No camera, or it was refused. The door still works without one. */
  noCamera: 'Không có camera — vẫn học được bình thường',

  // ---- enrolment, which is a consented act ------------------------------
  enrolTitle: 'Cho cô nhớ mặt con nhé',
  enrolName: 'Tên của con',
  /** The disclosure. It says what is kept and what is not. */
  enrolWhat:
    'Máy sẽ chụp ba khung hình và chỉ lưu lại các con số đặc trưng của khuôn mặt, '
    + 'ngay trên máy này. Ảnh không được lưu lại.',
  /** Consent is a deliberate act by someone who may give it. */
  enrolConsent: 'Con đã được thầy cô hoặc bố mẹ đồng ý cho đăng ký khuôn mặt',
  enrolGo: 'Đăng ký',
  enrolCancel: 'Thôi, để sau',
  enrolWorking: 'Đang chụp…',
  enrolDone: (name: string) => `Xong rồi, ${name}! Cô nhớ con rồi.`,
} as const
