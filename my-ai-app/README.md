# Huohuo AI VTuber

AI companion cá nhân với giao diện Live2D, chat, memory, mood, reminder, OCR và vision chat.

## Yêu cầu

- Node.js và npm hoặc pnpm
- Python 3.10+
- MySQL đang chạy nếu muốn dùng chat history, memory và reminder
- Ollama local hoặc Gemini API

## Cấu hình backend

```bash
cd backend
cp .env.example .env
```

Điền các biến trong `backend/.env`: provider/model LLM, thông tin MySQL và API key nếu dùng Gemini. Không commit hoặc chia sẻ file `.env`.

## Chạy development

Frontend:

```bash
npm install
npm run dev
```

Backend chạy tại `http://127.0.0.1:8000`:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Hoặc chạy `./start.sh` từ thư mục cha. Frontend mặc định gọi backend tại `http://127.0.0.1:8000`; có thể thay bằng `VITE_API_URL`.

## Kiểm tra

Frontend đã tách theo tính năng; xem [cấu trúc frontend](src/README.md) và [kiểm thử frontend](tests/README.md).
Đánh giá hội thoại thực tế với 30 lượt và audit tool bổ sung: [báo cáo chất lượng](backend/evaluations/conversation-quality.md).
Thay đổi tính cách, phân biệt người nói và dùng ký ức: [kết quả cải thiện hội thoại](backend/evaluations/dialogue-improvement.md).

```bash
npm run build
npm run lint
npm test
cd backend
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q api core services schemas config
```

Health check: `GET /health` thực hiện `SELECT 1` trên MySQL và kiểm tra metadata của model được cấu hình (Ollama `/api/show`, Gemini model lookup), có timeout. Trả `503` nếu một dịch vụ không sẵn sàng, kèm `checks` và lỗi model. Đây là kiểm tra khả dụng của model, không phải phép đo chất lượng hay tốc độ sinh câu trả lời.

Chat UI dùng `POST /api/chat/stream` để nhận SSE theo từng phần; endpoint `POST /api/chat` vẫn được giữ cho client không hỗ trợ stream. Ollama mặc định được giữ nóng (`OLLAMA_KEEP_ALIVE=-1`), context fast/deep dùng giới hạn riêng và log backend có `first_token_ms`, `total_llm_ms`, `tokens_per_sec`. SSE chỉ phát `complete` sau khi lưu câu trả lời vào MySQL. Lỗi model, JSON không hợp lệ, lỗi lưu dữ liệu hoặc stream bị ngắt được báo rõ; UI giữ câu hỏi và có nút thử lại. Không lưu fallback như câu trả lời của AI. Timeout của UI bao phủ cả quá trình đọc stream.

Ollama chat dùng [JSON Schema trong trường `format`](https://docs.ollama.com/capabilities/structured-outputs), tránh các đầu ra JSON rỗng thiếu `reply_vi`. Ngân sách đầu ra tối thiểu là 192 token cho fast và 384 cho deep để có chỗ cho cả nội dung và JSON; thời gian đọc context tối thiểu là 3 giây. Nếu không đọc được context, chat báo lỗi thay vì trả lời như thể bộ nhớ trống.

Các biến hiệu năng nằm trong `backend/.env.example`: `OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT_FAST`, `OLLAMA_NUM_PREDICT_DEEP`, các timeout Ollama và `LLM_CONTEXT_TIMEOUT_SECONDS`.

Ngữ cảnh hội thoại ngắn hạn mặc định giữ tối đa khoảng 6 lượt trao đổi gần nhất cho chat nhanh và 8 lượt cho câu sâu; các tin quá dài có thể khiến lượt cũ bị cắt trước. Giới hạn nằm ở `LLM_HISTORY_LIMIT_FAST`, `LLM_HISTORY_LIMIT_DEEP`, `LLM_MAX_CONTEXT_CHARS` và `OLLAMA_NUM_CTX` (mặc định 6144 token). Bộ phân loại ý định xem tối đa 5 lượt gần nhất để hiểu câu nối tiếp. Lịch sử MySQL vẫn được lưu riêng; việc tăng ngữ cảnh không thay đổi mốc quên của người dùng.

### Hội thoại và bộ nhớ cá nhân

- Giao diện hiển thị trạng thái kết nối, nút kiểm tra lại và lịch sử hội thoại tải từ MySQL. `GET /api/chat/history?user_id=default&limit=50` trả lịch sử để mở lại ứng dụng; `limit` tối đa 100.
- Trong **Bộ nhớ của bạn**, dùng **Sửa → Lưu** hoặc **×** để xóa. `PATCH /api/memories/{id}?user_id=default` nhận `{ "fact": "Thông tin mới" }`; endpoint xóa giữ nguyên. API trả 404 nếu không tìm thấy bộ nhớ của user đó, 503 nếu DB lỗi.
- Các câu trực tiếp như `Mình tên là Nguyễn Văn An`, `Mình thích trà`, `Mình học Python`, `Mình không còn thích trà nữa` được ghi nhận trước khi tạo câu trả lời. Đổi tên thay thế tên cũ; đổi sở thích hoặc ngừng học thay thế thông tin cùng chủ đề, giữ những chủ đề khác.
- Sau khi sửa/xóa hoặc thay thế thông tin cũ, hệ thống đặt mốc context trong bảng `memory_context_state`. Lịch sử trước mốc vẫn đọc được trên giao diện nhưng không được gửi lại cho LLM; việc này tránh thông tin đã quên quay lại từ lịch sử. Xóa/sửa tên cũng cập nhật hồ sơ và timeline. Đây không phải thao tác xóa toàn bộ bản ghi hội thoại.
- Tự trích xuất dùng các mẫu câu tiếng Việt trực tiếp, chưa xử lý mọi cách diễn đạt. Có thể sửa thủ công khi cần. Không trích xuất câu hỏi, câu được trích dẫn hoặc ví dụ có tiền tố.
- Chat và sửa/xóa bộ nhớ được tuần tự hóa theo user trong tiến trình. Chạy local với một worker; chưa hỗ trợ phối hợp khóa giữa nhiều worker hoặc xác thực nhiều tài khoản.

### Tính cách và ngữ cảnh hội thoại

- Giọng Huohuo được định nghĩa ở `backend/config/persona.py`: gần gũi, hơi nhút nhát, đùa nhẹ đúng chủ đề; không bắt buộc thêm câu hỏi, cảm thán hay lời khuyên. Prompt không ép tâm trạng suy ra từ một từ khóa lên câu trả lời mới.
- Ollama nhận lịch sử theo đúng vai `user`/`assistant`, có đại từ của người đang nói và các mở đầu gần đây để hạn chế lặp. Gemini hiện vẫn nhận ngữ cảnh dạng văn bản có nhãn vai; chưa kiểm tra chất lượng thực tế trên Gemini.
- Lấy tối thiểu 8 bản ghi lịch sử cho fast, 10 cho deep; chọn tối đa 8 ký ức theo từ khóa/chủ đề trong ít nhất 200 ký ức đang hoạt động gần nhất. Tên không được đưa vào mọi câu hỏi. Ngân sách ngữ cảnh mặc định 6000 ký tự; đây chưa phải tìm kiếm ngữ nghĩa trên toàn bộ ký ức.
- Có thể nói `Từ giờ gọi mình là cậu, xưng tớ nhé.` để lưu cách xưng hô qua các lượt. Hệ thống nhận câu trực tiếp dùng `mình`, `tôi`, `tớ`; bỏ đoạn code/lời trích dẫn trước khi trích xuất thông tin cá nhân. Những cách diễn đạt phức tạp vẫn có thể cần sửa thủ công.
- Các ý định hẹp như hỏi tên, việc học hiện tại, sở thích đã phủ định được trả lời trực tiếp từ dữ liệu khi nhận diện được. Ảnh chưa có hoặc ký ức chưa có được báo thiếu dữ liệu trong các mẫu câu hỗ trợ. Hội thoại còn lại vẫn dùng model, không có bảo đảm hết bịa hoặc hết nhầm vai.
- `timing.generation_path` phân biệt `model`, `grounded_memory`, `identity`, `missing_input`. Lượt không gọi model có `first_token_ms: null`, `total_llm_ms: 0`; không gộp chúng thành kết luận model sinh nhanh hơn. Ollama dùng temperature 0.4.

Đánh giá nội dung bằng transcript thật, bên cạnh unit test:

```bash
cd backend
venv/bin/python scripts/evaluate_conversations.py
venv/bin/python scripts/evaluate_dialogue_regressions.py
```

Script thứ hai kiểm tra phân biệt người dùng/người bạn/lời trích dẫn và giữ xưng hô. Mỗi lượt chạy tạo user riêng, lưu transcript và hash nguồn trong `backend/evaluations/`, rồi dọn dữ liệu thử. Cần đọc nội dung và audit công cụ; HTTP thành công không đồng nghĩa câu trả lời đạt chất lượng.

### Phản ứng Live2D theo lời trả lời

- Frontend chọn phản ứng từ `reply_vi` hoàn chỉnh. Trong lúc stream, nhân vật giữ trạng thái nhẹ nhàng; không diễn theo JSON còn dở hoặc tên motion/expression do model chọn tùy ý.
- Chào/cảm ơn dùng nét mặt `warm`; an ủi dùng `baozhen` (ôm gối); chúc mừng dùng `qizi` (cờ); tò mò dùng `haoqi`; chúc ngủ ngon dùng `keshui`. Giải thích kỹ thuật, code và trường hợp không rõ giữ bình thường. Không tự chọn giận dữ, mắt trắng hoặc hiệu ứng linh hồn.
- Lời hiện 4–30 giây theo độ dài và dấu câu, thay cho cố định 4/7 giây. Đây là ước lượng thời gian đọc khi chưa có TTS. Lịch sử chat vẫn giữ lời trả lời để đọc lại.
- Phản ứng giữ tối đa 3,5–8 giây tùy loại, không lâu hơn lời hiển thị. Motion không lặp và có thể dừng trước khi hết một chu kỳ nếu câu ngắn. Cùng động tác có khoảng nghỉ 12 giây; nét mặt vẫn có thể phản hồi.
- Trả biểu cảm về mặc định bằng API reset thực sự; đưa tư thế/đạo cụ về trạng thái ban đầu trong khoảng 350 ms. Gửi câu mới, dừng khẩn cấp, ẩn tab hoặc unmount đều hủy phản ứng cũ, kể cả khi asset đang tải. Tắt động tác lớn khi hệ điều hành yêu cầu giảm chuyển động.
- Bộ chọn hiện dùng quy tắc cụm từ, chưa hiểu hoàn hảo câu mỉa mai hoặc nhiều sắc thái. Build/lint và test điều phối không thay thế việc nhìn model chạy thực tế; xem checklist trong [tests/README.md](tests/README.md).

Kiểm thử tích hợp với MySQL và model thật (tạo user thử riêng, tự dọn dữ liệu thử):

```bash
cd backend
venv/bin/python scripts/verify_local.py
```

Bài kiểm tra đi qua API ASGI, xác minh streaming, đọc lại lịch sử bằng client mới, thay đổi sở thích, sửa/xóa tên và ngữ cảnh được gửi cho model. Kiểm tra giao diện trình duyệt vẫn là bước riêng.

WebSocket agent events: `ws://127.0.0.1:8000/api/ws?user_id=default`. Kết nối này nhận `agent_output` và `assistant_response`; gửi `ping` để kiểm tra kết nối.

Notes tool:

- `POST /api/tools/notes?user_id=default` với `{ "title": "...", "content": "...", "tags": ["..." ] }`
- `GET /api/tools/notes?user_id=default&search=...`
- `GET /api/tools/notes/{note_id}?user_id=default`
- `PATCH /api/tools/notes/{note_id}?user_id=default`
- `POST /api/tools/notes/{note_id}/archive?user_id=default`

Notes được archive thay vì xóa cứng và mọi truy vấn đều giới hạn theo `user_id`.

Giai đoạn 5 — Goal Manager và Planner:

- `POST /api/goals` tạo mục tiêu dài hạn.
- `GET /api/goals` liệt kê mục tiêu.
- `PATCH /api/goals/{goal_id}` cập nhật trạng thái hoặc tiến độ.
- `POST /api/goals/{goal_id}/plan` tạo kế hoạch; bỏ qua `steps` để dùng plan mặc định.
- `GET /api/goals/{goal_id}` xem goal cùng các bước.
- `PATCH /api/goals/steps/{step_id}` cập nhật tiến độ từng bước.

Goal và step đều được cô lập theo `user_id`; tiến độ goal được đồng bộ từ trung bình tiến độ các step.

Research Agent:

- `POST /api/research?user_id=default` với `{ "query": "...", "max_sources": 3, "save": true }`.
- `GET /api/knowledge?user_id=default` đọc các nghiên cứu đã lưu.
- Pipeline giới hạn tối đa 5 nguồn, lọc URL public, timeout đọc nguồn và giới hạn nội dung trước khi đưa vào LLM.

Long-term Knowledge Memory và Progress Evaluator:

- `GET /api/long-term-memory?user_id=default` trả riêng `personal`, `knowledge` và `experiences`.
- `POST /api/experiences?user_id=default` lưu bài học/kinh nghiệm.
- `GET /api/experiences?user_id=default` đọc kinh nghiệm đã lưu.
- `GET /api/progress/evaluate?user_id=default` đánh giá goal: `on_track`, `at_risk`, `stalled`, `overdue` hoặc `completed`.

Chủ động có ngữ cảnh:

- Chỉ gợi chuyện khi cửa sổ đang được sử dụng, không gõ, không đọc bong bóng thoại, không nghe mic và không xử lý câu trả lời. Heartbeat mỗi 15 giây, hết hiệu lực sau 45 giây; giờ yên lặng mặc định 22:00–08:00 theo máy người dùng.
- Sau ít nhất 5 phút từ tin nhắn cuối (không quá 8 giờ), chọn sở thích/việc đang học hoặc goal đang trễ có liên quan đến lời **người dùng** vừa nói và ký ức còn hiệu lực. Không có chủ đề phù hợp thì giữ im lặng.
- Chỉ mời trò chuyện một lần khi chưa được trả lời; cách nhau tối thiểu 15 phút, tối đa 3 lần/giờ trong một tiến trình. Chủ đề vừa dùng được giữ lại để tránh lặp trong 24 giờ. Trạng thái chờ trả lời và thời điểm gửi được lưu MySQL qua lần khởi động lại.
- Checkbox **Cho phép Huohuo chủ động bắt chuyện** lưu theo user. Có thể nhắn “Mình muốn yên lặng”, “Đừng làm phiền 10 phút” (thời lượng số, tối đa 24 giờ), hoặc “Bạn chủ động bắt chuyện lại nhé”. “Mình đi ngủ”/“Mình đang tập trung” giữ yên lặng đến tin nhắn tiếp theo. Tắt chủ động vẫn cho phép chat trực tiếp.
- Reminder đến hạn được ưu tiên khi được phép ngắt lời; vẫn xem được trong bảng nhắc việc khi đang yên lặng. Không tạo tin nhắn giả của người dùng để nhắc việc, không tự hoàn thành reminder hay sửa goal.
- Đề xuất WebSocket hết hạn sau 30 giây. Chỉ lưu lời chủ động vào lịch sử assistant sau xác nhận hiển thị của frontend và kiểm tra lại ngữ cảnh. Đề xuất bị bỏ qua cũng tạm ngừng gợi chuyện đến tin nhắn tiếp theo, tránh thử lại liên tục.
- `GET/PATCH /api/proactive/preferences?user_id=...` đọc/lưu tùy chọn (`{"enabled": true}`). `GET /api/proactive/status` xem cấu hình; `POST /api/proactive/check` chạy một lượt quét, vẫn áp dụng các điều kiện trên.
- Cơ chế hiện dùng quy tắc tiếng Việt và mẫu câu có ngữ cảnh, chưa phải bộ hiểu ý định tự do. Presence chỉ gửi cờ trạng thái và giờ địa phương, không gửi nội dung đang gõ. Chạy một backend worker để giữ nhất quán presence/budget.
- Kiểm tra tích hợp MySQL riêng: từ `backend`, chạy `venv/bin/python scripts/verify_proactive.py`; script chỉ tạo/xóa dữ liệu của user thử mới và không gọi LLM.

Autonomous Loop nâng cao và Self-learning an toàn:

- Autonomous loop chạy định kỳ với cooldown, giới hạn event mỗi chu kỳ/cửa sổ thời gian và emergency stop.
- `GET /api/proactive/status` hiển thị các giới hạn đang áp dụng.
- `GET /api/self-learning/policy` hiển thị policy self-learning.
- `POST /api/self-learning/learn?user_id=default` chỉ nhận `target` là `memory`, `knowledge` hoặc `experience`.
- Tool `self_learn` dùng cùng policy và rate limit; không có quyền sửa code, file hệ thống, quyền truy cập hoặc cấu hình máy.

Mood và Relationship Manager:

- `GET /api/mood/summary?user_id=default` trả mood hiện tại, mood chiếm ưu thế, xu hướng dài hạn và phân phối cảm xúc.
- `POST /api/mood/analyze?message=...` phân tích tín hiệu cảm xúc mà không tự ghi dữ liệu.
- `GET /api/relationship?user_id=default` trả mức thân thiết, stage, tone và số lần tương tác.
- Sau mỗi tin nhắn, backend ghi nhận cả tương tác trung tính để relationship history không bị đứt quãng.

Personality Engine:

- `GET /api/personality` trả personality contract dạng read-only.
- Danh tính, trait cốt lõi, giọng nói và ranh giới được giữ cố định trong một engine dùng chung.
- Mood và relationship chỉ thay đổi độ ấm/cách diễn đạt, không thay đổi vai trò hay nguyên tắc của Huohuo.

Tool runtime:

- `POST /api/tools/execute` nhận `{ "name": "...", "arguments": {...} }`.
- `GET /api/tools/audit?user_id=default` xem audit metadata của tool.
- LLM có thể trả `tool_calls`; backend giới hạn tối đa 3 call mỗi lượt, có timeout và rate limit.
- `write_file` chỉ làm việc trong `TOOL_FILE_ROOT`, chỉ nhận file văn bản được allowlist và yêu cầu confirmation token.
- `web_search` có giới hạn tổng 10 giây, tối đa 2 lần thử với lỗi tạm thời và tối đa 8 kết quả hợp lệ.

## Quyền riêng tư và an toàn

- Microphone và screen capture bị từ chối mặc định ở backend.
- Browser luôn hỏi quyền microphone/chia sẻ màn hình trước khi sử dụng.
- Nút `🛑 Dừng` thu hồi quyền capture và dừng autonomous agent.
- Audit privacy chỉ lưu loại hành động và metadata tối thiểu, không lưu nội dung audio/ảnh/tài liệu.
- Xem consent: `GET /api/privacy/consent?user_id=default`.
- Xem audit: `GET /api/privacy/audit?user_id=default`.

## Lưu ý

Đây là ứng dụng cá nhân chạy local; chưa có authentication cho nhiều tài khoản. Không expose backend ra internet nếu chưa bổ sung authentication và authorization. MySQL phải chạy trước khi kiểm tra đầy đủ memory, history và reminder.


Tra cứu thông tin hiện tại (2026-09-11): câu hỏi như “Hiện tại Đấu trường chân lý đang là mùa bao nhiêu” được bắt buộc tra web. Truy vấn kèm ngày Việt Nam và yêu cầu SearXNG `time_range=day` cho tỷ giá/thời tiết/hôm nay, `month` cho các truy vấn hiện tại khác; giữ URL/ngày đăng, phân biệt ngày truy cập với ngày xuất bản. Bộ lọc phụ thuộc engine và không bảo đảm nguồn mới. Nếu tra cứu thất bại/rỗng, nhánh trả lời có căn cứ trả trực tiếp thông báo chưa xác minh, không dùng phỏng đoán cũ. Khi có nguồn, việc phân tích mới/cũ và trích dẫn vẫn phụ thuộc mô hình; chưa có kiểm chứng nội dung toàn trang trong nhánh chat này.


Phân loại ý định theo ngữ cảnh:

- `services/intent_service.py` phân loại hỏi thông tin, hỏi ý kiến, tâm sự, ký ức cá nhân, xã giao, hành động, sáng tạo và thiếu chủ đề. Kết quả chọn nguồn conversation/memory/web, nhu cầu thông tin mới và truy vấn.
- Câu rõ nghĩa dùng quy tắc nhanh. Câu chưa rõ dùng tối đa 6 lượt gần nhất sau mốc xóa ký ức, giới hạn 500 ký tự/lượt, gửi đến Ollama đang cấu hình để phân loại JSON. Giới hạn 8 giây; đầu ra sai định dạng, độ tin cậy dưới 0.75 hoặc tham chiếu assistant làm chủ đề tìm kiếm đều bị loại. Điểm confidence do mô hình tự báo, không phải xác suất đã hiệu chuẩn.
- Khi phân loại lỗi, thử nối câu nói tiếp với chủ đề người dùng vừa nhắc; không lấy lời assistant làm sự thật. Thiếu chủ đề thì hỏi lại. Gemini hiện dùng quy tắc/dự phòng, chưa gọi mô hình phân loại riêng.
- Cả chat thường và streaming dùng cùng bộ định tuyến. Ý định web gọi tìm kiếm; các ý định còn lại giữ luồng hội thoại/ký ức và công cụ hiện có. Phân loại action không cấp thêm quyền thực thi. Không lưu nhãn phân loại hoặc truy vấn vào ký ức; log chỉ ghi nhãn/phương pháp, không ghi nội dung chat.
- Kiểm tra mô hình cục bộ không ghi DB: từ backend chạy `venv/bin/python scripts/verify_intent.py`. Kết quả ở `evaluations/intent-verification.json`. Phân loại bằng mô hình có thể cộng thêm tối đa 8 giây vào các câu mơ hồ; các câu nhiều ý định/phủ định phức tạp chưa được bảo đảm xử lý đúng hoàn toàn.


Lời chào nhanh: các câu chào thuần túy như `hi`, `hello`, `chào Huohuo`, `xin chào bạn nhé` bỏ qua cả mô hình phân loại và sinh văn bản. Vẫn đọc ngữ cảnh để giữ cách xưng hô, lưu lịch sử và áp dụng quyền như trước; không áp dụng cho lời chào kèm câu hỏi/tâm sự. Timing hiển thị `Chào nhanh`, `Định tuyến` (bao gồm tra web nếu có), `First token`, `LLM` và tổng thời gian phía frontend. Đường chào không sinh token nên First token/tok/s để trống và LLM=0; điều này không có nghĩa tổng thời gian bằng 0 vì vẫn có DB/network. Kiểm tra: 198 backend tests, 42 frontend tests, build/lint qua; chưa đo lại tổng thời gian trên phiên trình duyệt thật của người dùng.


Giọng Huohuo:

- Prompt tại `backend/config/persona.py`: nhịp ngắn, hơi rụt rè nhưng có chính kiến, đùa từ tình huống đang nói. Khi người dùng mệt/buồn hoặc yêu cầu dừng trêu thì dịu lại; không biến mọi chủ đề thành ma quỷ, không lắp bắp liên tục. Câu hỏi kỹ thuật ưu tiên đúng và rõ; ví dụ trong prompt không phải ký ức.
- Lời chào nhanh và giới thiệu tại `backend/services/dialogue_policy_service.py` dùng cùng giọng, theo xưng hô đã lưu; ba mẫu chào luân phiên theo lịch sử và không hỏi dồn. Câu chào kèm yêu cầu vẫn vào luồng hội thoại đầy đủ.
- Bộ 18 lượt đánh giá tại `backend/evaluations/huohuo-scenarios.json`, chia thành `huohuo_voice`, `huohuo_boundaries`, `huohuo_grounding`, `huohuo_greetings`. Từ backend chạy `venv/bin/python scripts/evaluate_conversations.py --scenario huohuo_voice` (hoặc tên nhóm khác). Đây là kiểm tra API thật với người dùng thử tự dọn dữ liệu; xem câu trả lời và tiêu chí từng lượt, không coi HTTP thành công là đạt chất lượng tính cách.

Định tuyến tỷ giá: câu “huohuo cho biết tỷ lệ usd vnd hôm nay được không”, mã cặp USD/VND hoặc USDVND, và yêu cầu quy đổi có mã tiền tệ được xử lý bằng quy tắc trực tiếp sang web, không chờ phân loại bằng mô hình. Cách viết “tỷ lệ” được chuẩn hóa thành “tỷ giá” trong truy vấn. Kiểm thử gồm câu nguyên văn, các biến thể, truy vấn lịch sử và trường hợp chỉ bình luận về thiết kế tiền.


Ổn định tra cứu:

- Dùng cùng `rule_intent` cho kiểm tra cần web và định tuyến chat, hỗ trợ lời đề nghị dài; loại nội dung trích dẫn khỏi quy tắc và tôn trọng yêu cầu không tra cứu.
- Múi giờ Việt Nam dùng `Asia/Ho_Chi_Minh` (tên IANA; `Asia/Ha_Noi` không hợp lệ).
- SearXNG retry tối đa một lần khi lỗi mạng/timeout/429/502/503/504, tổng ngân sách 10 giây. Lỗi 403 (thường do chưa bật JSON), dữ liệu sai định dạng và cấu hình provider sai được báo riêng; không tự đổi nhà cung cấp tìm kiếm.
- Loại URL không phải HTTP(S), URL có thông tin đăng nhập, kết quả không có đoạn trích và bản trùng URL. Giữ ngày đăng riêng với thời điểm tra cứu; loại kết quả có ngày quá cũ/tương lai xa khỏi câu hỏi hiện tại. Nguồn không có ngày vẫn được đánh dấu chưa xác định, không được coi là mới chỉ vì vừa tìm thấy.
- Chat trả trường `search` gồm trạng thái, số nguồn, nguồn thiếu ngày, số lần thử và lỗi kỹ thuật. Giao diện hiển thị số nguồn hoặc lý do chưa có nguồn; URL vẫn không xuất hiện trong lời thoại. Khi không còn nguồn phù hợp, nhánh trả lời trực tiếp nói chưa xác minh được.
- Từ backend, chạy `venv/bin/python scripts/verify_search.py` để thử định tuyến thật cho tỷ giá/TFT. Script không gọi LLM hoặc ghi lịch sử. Xem `evaluations/search-verification.json`; có trạng thái tra cứu không đồng nghĩa câu trả lời cuối đã chính xác.
- SearXNG là dịch vụ riêng: nếu dùng Docker, Docker Desktop và container SearXNG phải đang chạy; API JSON phải được bật. Nhánh chat vẫn dùng đoạn trích, chưa đọc và đối chiếu toàn bộ nội dung từng trang.


Giao diện gọn và desktop:

- Màn hình chính chỉ còn Huohuo, lời thoại và thanh nhập với nút công cụ, micro, gửi. Bỏ bảng lịch sử và chỉ số tương tác khỏi giao diện; dữ liệu vẫn được giữ cho ngữ cảnh.
- Biểu tượng bốn ô mở bảng công cụ; Escape hoặc nút đóng trả lại màn hình nhân vật. Bộ nhớ, nhắc việc, đọc ảnh/tài liệu, tùy chọn chủ động, dừng hoạt động và thông tin kết nối nằm trong bảng này.
- Chạy `npm run desktop` hoặc mở `Huohuo.command` để dùng cửa sổ desktop luôn nổi. Kéo phần tiêu đề để di chuyển; tắt ghim trong Công cụ. Xem `desktop/README.md` về khởi động backend, giới hạn mic/chụp màn hình và các bước kiểm tra thủ công.
