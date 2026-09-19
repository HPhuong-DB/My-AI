# Cải thiện hội thoại Huohuo — 11/09/2026

Đã cải thiện rõ các ca nhớ dữ kiện cá nhân và phân biệt người nói trong mẫu thử. Giọng trò chuyện tự do vẫn chưa ổn định: có câu chung chung, xưng hô bị trượt và yêu cầu công cụ chưa được thực hiện đúng.

## Thay đổi đã triển khai

- Persona gọn hơn: nhút nhát, gần gũi, đùa nhẹ theo chủ đề; không ép cảm thán, lời khuyên hay câu hỏi cuối. Bỏ câu mẫu sau khi phát hiện model sao chép sang chủ đề khác. Không để mood suy ra từ từ khóa lấn át phủ định mới nhất.
- Ollama nhận các lượt `user`/`assistant` riêng, có hướng dẫn đại từ và mở đầu gần đây. Không coi câu trợ lý từng nói là bằng chứng về người dùng.
- Chọn ký ức liên quan theo từ khóa/chủ đề; không chèn tên hoặc lời nhắc “chưa biết tên” vào mọi câu hỏi. Giữ nguyên cơ chế loại ngữ cảnh cũ khi sửa/xóa ký ức.
- Lưu yêu cầu xưng hô như “gọi mình là cậu, xưng tớ”, dùng cả `mình/tôi/tớ` khi trích xuất câu trực tiếp. Loại đoạn code/lời trích dẫn trước khi lưu thông tin cá nhân.
- Với các ý định hẹp đã nhận diện, trả lời từ dữ liệu: tên, việc học, sở thích đã thay đổi, tên người dùng và người bạn được nhắc đến. Không đoán ảnh chưa nhận hoặc ký ức chưa có trong các mẫu câu được hỗ trợ.
- Giữ xuống dòng khi làm sạch đầu ra. Sửa lỗi serialize datetime trong kết quả công cụ. Câu nhật ký có “hôm nay” không tự kích hoạt tìm kiếm web chỉ vì cụm từ này.

## Kiểm tra

**163 unit/integration tests có mock đều đạt.** [Log kiểm tra](dialogue-tests.log) có lỗi cố ý của test Executor và thông báo MySQL bị sandbox chặn; kết luận của suite là `OK`. Kiểm tra riêng với MySQL/Ollama thật bằng `scripts/verify_local.py` cũng đạt: streaming, tải lại lịch sử, phủ định sở thích, sửa tên An → Bình, xóa tên và không lấy lại từ ngữ cảnh cũ. Dữ liệu thử đã được dọn.

**Bộ 30 lượt:** [transcript sau sửa](eval-c69e0091fee9.json) đạt 30/30 request về mặt kỹ thuật. Chấm thủ công theo cùng rubric baseline: **21 đạt, 7 một phần, 2 không đạt**, so với **13/10/7** trước đó. Xem [chấm từng lượt](dialogue-improvement-review.json) và [baseline](conversation-review.json).

Chín lượt trong bộ này dùng policy trả lời từ dữ liệu, không gọi model. Các ca tên/việc học/sở thích được sửa, không còn bịa món ăn, ảnh hay tên mèo trong mẫu này. Hai ca không đạt là lưu/đọc ghi chú: audit và danh sách note đều rỗng dù lời trả lời hứa hoặc khẳng định đã lưu.

**Bộ bổ sung 11 lượt:** [transcript bản cuối](eval-2759b71b0e27.json) đạt 11/11 request; đọc nội dung thấy phân biệt đúng Hải/Mai và Mai là người học piano. Không gán lời trích dẫn của Mai thành thông tin của Hải. Tuy nhiên gợi ý hoạt động còn vòng vo. Chuỗi xưng hô gọi “cậu” được giữ, nhưng hai lượt vẫn dùng lại “mình”; một câu phản ứng về bức tranh còn gượng. Đây cũng là bộ đã dùng trong quá trình sửa, không còn là hold-out độc lập.

**Mức lặp:** chỉ báo đơn giản “ba từ mở đầu trùng một trong ba câu model gần nhất cùng hội thoại” ghi nhận 1 lần ở baseline và 1 lần sau sửa. Chưa có bằng chứng đủ mạnh để nói mức lặp đã giảm; thay đổi hiện có là cung cấp lịch sử và ràng buộc tránh lặp cho model.

## Giới hạn của kết quả

- Trợ lý tự đọc và chấm, không có người chấm mù độc lập. Bộ câu hỏi đã dùng để phát triển; một lượt chạy không cho biết độ ổn định dài hạn. Đã đổi cả prompt, context, policy và temperature Ollama 0.7 → 0.4, không tách được tác động từng thay đổi.
- Các file JSON có hash nguồn. Bộ 30 lượt được chạy trước lần chỉnh cuối chỉ thay cách thay đại từ trong policy và mở rộng mẫu “bạn tôi/tớ”. Bộ 11 lượt khớp toàn bộ hash nguồn cuối; unit test bổ sung xác nhận đại từ không sửa nhầm từ bên trong dữ kiện.
- Model vẫn có thể nhầm vai, sai định dạng hai dòng, thêm câu hỏi thừa hoặc bịa hành động công cụ. Chưa thay model, chưa thêm TTS, chưa kiểm tra Gemini hoặc biểu cảm trên trình duyệt.
- Trích xuất và chọn ký ức vẫn dựa trên mẫu câu/từ khóa, có giới hạn số bản ghi và độ dài. Policy là các trường hợp hẹp, không phải bảo đảm hiểu mọi câu tiếng Việt.

## Chạy lại

Từ thư mục `backend`, chạy `venv/bin/python -m unittest discover -s tests -p 'test_*.py'`, sau đó `scripts/evaluate_conversations.py`, `scripts/evaluate_dialogue_regressions.py` và `scripts/verify_local.py` bằng cùng Python trong venv. Các script thực tế cần MySQL/Ollama hoạt động; tạo user thử riêng và tự dọn dữ liệu.
