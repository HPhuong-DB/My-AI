import { useCallback, useEffect, useRef, useState } from 'react';
import { requestJSON, setPrivacyConsent, USER_ID, formatDuration } from '../api/client';
import type { Activity } from './useActivity';
interface PerceptionResponse { text?: string; reply_vi?: string; ocr?: { text?: string }; filename?: string; char_count?: number; }
export function usePerception({ begin, end }: Activity, onDraft: (text: string) => void) {
  const [ocrResult, setOcrResult] = useState("");
  const [ocrError, setOcrError] = useState("");
  const [imageComment, setImageComment] = useState("");
  const [imageCommentError, setImageCommentError] = useState("");
  const [selectedImageName, setSelectedImageName] = useState("");
  const [isCapturingScreen, setIsCapturingScreen] = useState(false);
  const [documentText, setDocumentText] = useState("");
  const [documentError, setDocumentError] = useState("");
  const [isReadingDocument, setIsReadingDocument] = useState(false);
  const [timing, setTimingText] = useState('');
  const [status, setVoiceStatus] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const documentFileInputRef = useRef<HTMLInputElement>(null);
  const imageFileRef = useRef<File | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const screenRef = useRef<MediaStream | null>(null);
  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    screenRef.current?.getTracks().forEach((track) => track.stop());
    void setPrivacyConsent('screen', false);
  }, []);
  useEffect(() => cancel, [cancel]);
  const MAX_OCR_FILE_BYTES = 5 * 1024 * 1024;
  const handleOcrFile = async (file: File | null) => {
    if (!file) {
      setOcrError("Không có file để xử lý");
      return;
    }

    const allowedTypes = ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"];
    if (!allowedTypes.includes(file.type)) {
      setOcrError("Chỉ hỗ trợ JPG, PNG, WEBP, BMP hoặc TIFF.");
      return;
    }
    if (file.size > MAX_OCR_FILE_BYTES) {
      setOcrError("Ảnh OCR không được vượt quá 5 MB.");
      return;
    }

    if (!begin()) return;
    controllerRef.current = new AbortController();
    setOcrError("");
    setOcrResult("");
    setImageComment("");
    setImageCommentError("");
    imageFileRef.current = file;
    setSelectedImageName(file.name);
    const clientStartedAt = performance.now();
    setTimingText("Đang đo thời gian OCR...");

    const formData = new FormData();
    formData.append("image", file);

    try {
      const data = await requestJSON<PerceptionResponse>(`/api/ocr`, {
        method: "POST",
        signal: controllerRef.current?.signal,
        body: formData,
      });


      const completedAt = performance.now();
      setOcrResult(data.text || "Không tìm thấy văn bản");
      setTimingText(`OCR API + xử lý: ${formatDuration(completedAt - clientStartedAt)}`);
      console.info("⏱️ OCR timing", {
        totalMs: Math.round(completedAt - clientStartedAt),
      });
      setVoiceStatus("Đã nhận OCR. Bạn có thể gửi để chat.");

      if (data.text) {
        onDraft(data.text);
      }
    } catch (error) {
      console.error(error);
      setTimingText(`OCR lỗi sau ${formatDuration(performance.now() - clientStartedAt)}`);
      setOcrError("OCR thất bại. Hãy thử lại với ảnh khác.");
      setVoiceStatus("OCR lỗi. Kiểm tra ảnh hoặc server.");
    } finally {
      end();
    }
  };

  const handleImageComment = async () => {
    const file = imageFileRef.current;
    if (!file || !begin()) return;
    controllerRef.current = new AbortController();

    const clientStartedAt = performance.now();
    const formData = new FormData();
    formData.append("image", file);
    formData.append("ocr_text", ocrResult);
    formData.append(
      "question",
      "Hãy nhận xét nội dung bức ảnh và giải thích hoặc dịch những từ ngữ đáng chú ý nếu có.",
    );

    setImageComment("");
    setImageCommentError("");
    setTimingText("Đang phân tích ảnh bằng AI...");

    try {
      const data = await requestJSON<PerceptionResponse>(`/api/image-chat`, {
        method: "POST",
        signal: controllerRef.current?.signal,
        body: formData,
      }, 50_000);

      const totalMs = performance.now() - clientStartedAt;
      setImageComment(data.reply_vi || "AI chưa đưa ra nhận xét.");
      setTimingText(`AI phân tích ảnh: ${formatDuration(totalMs)}`);
      console.info("⏱️ Image analysis timing", { totalMs: Math.round(totalMs) });
    } catch (error) {
      console.error("Lỗi phân tích ảnh:", error);
      setImageCommentError("Không thể phân tích ảnh. Kiểm tra Gemini API hoặc thử lại.");
      setTimingText(`AI ảnh lỗi sau ${formatDuration(performance.now() - clientStartedAt)}`);
    } finally {
      end();
    }
  };

  const handleScreenCapture = async () => {
    if (isCapturingScreen) return;
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setImageCommentError("Trình duyệt không hỗ trợ chia sẻ màn hình.");
      return;
    }

    if (!begin()) return;
    const captureController = new AbortController();
    controllerRef.current = captureController;
    let stream: MediaStream | null = null;
    setIsCapturingScreen(true);
    setImageCommentError("");
    setTimingText("Đang chờ quyền xem màn hình...");

    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });
      screenRef.current = stream;
      if (captureController.signal.aborted) throw new DOMException("Cancelled", "AbortError");
      if (!(await setPrivacyConsent("screen", true))) {
        throw new Error("Không lưu được quyền phân tích màn hình");
      }
      if (captureController.signal.aborted) throw new DOMException("Cancelled", "AbortError");
      const track = stream.getVideoTracks()[0];
      if (!track) throw new Error("Không lấy được video màn hình");

      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      await video.play();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

      const settings = track.getSettings();
      const width = video.videoWidth || Number(settings.width) || 1280;
      const height = video.videoHeight || Number(settings.height) || 720;
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d")?.drawImage(video, 0, 0, width, height);

      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("Không tạo được ảnh chụp màn hình");

      const formData = new FormData();
      formData.append("image", blob, "screen-capture.png");
      formData.append("user_id", USER_ID);
      formData.append("question", "Bạn đang làm gì trên màn hình? Hãy tóm tắt nội dung chính.");

      setTimingText("Huohuo đang phân tích màn hình...");
      const data = await requestJSON<PerceptionResponse>(`/api/perception/screen`, {
        method: "POST",
        signal: controllerRef.current?.signal,
        body: formData,
      }, 60_000);

      setImageComment(data.reply_vi || "Huohuo chưa đọc được màn hình này.");
      setOcrResult(data.ocr?.text || "");
      setTimingText("Đã phân tích màn hình.");
    } catch (error) {
      if ((error as DOMException).name === "AbortError") {
        setImageCommentError("Đã hủy quyền chia sẻ màn hình.");
      } else {
        console.error("Lỗi phân tích màn hình:", error);
        setImageCommentError("Không thể phân tích màn hình. Kiểm tra Gemini Vision rồi thử lại.");
      }
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      screenRef.current = null;
      void setPrivacyConsent("screen", false);
      setIsCapturingScreen(false);
      end();
    }
  };

  const handleDocumentFile = async (file: File | null) => {
    if (!file || isReadingDocument || !begin()) return;
    controllerRef.current = new AbortController();
    setIsReadingDocument(true);
    setDocumentError("");
    setDocumentText("");
    setTimingText("Đang đọc tài liệu...");

    try {
      const formData = new FormData();
      formData.append("document", file);
      formData.append("user_id", USER_ID);
      formData.append("question", "Hãy đọc và tóm tắt những nội dung chính trong tài liệu này.");
      const data = await requestJSON<PerceptionResponse>(`/api/perception/document`, {
        method: "POST",
        signal: controllerRef.current?.signal,
        body: formData,
      }, 60_000);

      setDocumentText(data.text || "Tài liệu không có nội dung văn bản.");
      setTimingText(`Đã đọc ${data.filename || file.name} · ${data.char_count || 0} ký tự`);
    } catch (error) {
      console.error("Lỗi đọc tài liệu:", error);
      setDocumentError("Không thể đọc tài liệu. Kiểm tra định dạng và thử lại nhé.");
    } finally {
      setIsReadingDocument(false);
      end();
      if (documentFileInputRef.current) documentFileInputRef.current.value = "";
    }
  };

  const onEvent = useCallback((payload: Record<string, unknown>) => {
    const vision = (payload.vision_analysis ?? payload.vision) as Record<string, unknown> | undefined;
    const summary = typeof vision?.summary === 'string' ? vision.summary : typeof payload.vision_comment === 'string' ? payload.vision_comment : '';
    const ocr = payload.ocr as Record<string, unknown> | undefined;
    if (summary) setImageComment(summary);
    if (typeof ocr?.text === 'string') setOcrResult(ocr.text);
    if (typeof payload.text === 'string') setDocumentText(payload.text);
  }, []);
  return { ocrResult, ocrError, imageComment, imageCommentError, documentText, documentError, selectedImageName, isCapturingScreen, isReadingDocument, fileInputRef, documentFileInputRef, handleOcrFile, handleImageComment, handleScreenCapture, handleDocumentFile, timing, status, onEvent, cancel };
}
