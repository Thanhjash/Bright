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
} as const satisfies Record<string, RoomLabel>

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
