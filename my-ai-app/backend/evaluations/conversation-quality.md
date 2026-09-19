# Đánh giá hội thoại Huohuo — 10/09/2026

Kết luận: hệ thống hoàn thành request ổn định trong mẫu thử, nhưng chất lượng hội thoại chưa đủ tin cậy cho một companion cá nhân tự chủ. Cần ưu tiên chống bịa ký ức/ảnh, thực thi tool và trả lời đúng chủ đề trước khi tăng mức chủ động.

## Phạm vi và phương pháp

- 30 lượt qua API chat streaming thật, chia 7 hội thoại, mỗi hội thoại dùng user thử riêng; giữ ngữ cảnh giữa các lượt cùng nhóm.
- Ollama `gemma3:4b`, temperature 0.7, context 4096, ngân sách fast tối thiểu 192/deep 384 token. Không thay prompt hay backend trong lần đánh giá này.
- Thời gian: 16:45:57–16:50:49 giờ Việt Nam. Một lượt chạy mỗi tình huống; không suy ra tỷ lệ ổn định dài hạn hoặc chất lượng của mọi model.
- Chấm thủ công bởi trợ lý từ transcript, không có người chấm độc lập: 2 = đạt; 1 = đạt một phần; 0 = không đạt. Lời nhắc uống nước thiếu thời điểm là tình huống mơ hồ, không coi nhắc ngay bằng lời là hành vi bịa đặt.
- Chưa đánh giá TTS hoặc trực quan biểu cảm Live2D. Bộ test kỹ thuật không thay thế đánh giá nội dung.
- Dữ liệu thử đã xóa khỏi MySQL; transcript giả lập và cấu hình được lưu trong các file kết quả để kiểm tra lại.

## Kết quả

- Kỹ thuật: 30/30 có sự kiện complete, 0 lỗi API/fallback trong mẫu này.
- Nội dung: 13/30 đạt, 10/30 đạt một phần, 7/30 không đạt theo rubric trên.
- Độ trễ tổng: trung vị **9,05 giây**, p95 **18,62 giây**, lớn nhất **21,04 giây**.
- First token theo log backend: trung vị **4,09 giây**, p95 **10,74 giây**. Đây là token đầu của model, chưa phải ký tự đầu người dùng nhìn thấy; client ASGI gom response nên không đo độ trễ render trên trình duyệt.
- p95 dùng nearest-rank trên 30 mẫu. Tốc độ sinh token trung vị **10,82 token/giây**.
- Model chọn expression `qizi2` ở 21/30 lượt. Chỉ cho thấy mức tập trung lựa chọn; chưa kết luận biểu cảm nhìn trên avatar có phù hợp không.

## Các lỗi cần ưu tiên

1. **Bịa dữ liệu chưa có**: nói người dùng thích phở, bịa ảnh mèo đen trên sofa, bịa tên mèo Meow Meow. Cần kiểm tra đầu vào thực sự có ảnh và trả lời rõ chưa biết khi thiếu ký ức.
2. **Không thực hiện công cụ**: yêu cầu lưu/đọc note bị trả lời bằng lời hứa hoặc câu hỏi thừa. Chạy bổ sung 3 lượt với audit: không có tool call và không có note nào được lưu. Đây là thiếu thực thi, không chỉ vấn đề giọng văn.
3. **Sai trọng tâm**: câu hỏi thời tiết Atlantis lại được trả lời bằng việc chưa lưu tên. Có dấu hiệu chỉ dẫn về tên được áp dụng sai ngữ cảnh; cần kiểm tra prompt/routing riêng, chưa khẳng định nguyên nhân từ một lượt.
4. **Phủ định và chuyển trạng thái chưa tự nhiên**: dữ kiện mới có thể được nhớ đúng nhưng diễn đạt vòng vo, hỏi lặp hoặc thêm lý do không được cung cấp.
5. **Giọng nói và chỉ dẫn định dạng**: còn nhiều câu mở đầu theo mẫu, tự gán trải nghiệm uống nước/ngủ, chưa tuân thủ hai dòng. Backend có bước làm sạch whitespace; cần phân biệt lỗi model với lỗi hậu xử lý trước khi chỉnh prompt.

## Những phần đang làm được

- Nhớ đúng tên Linh và đang học Python trong cùng hội thoại.
- Hiểu yêu cầu chưa đưa lời khuyên và tôn trọng yêu cầu im lặng.
- Nhận ra mỉa mai khi người dùng mất bài; chúc mừng gắn với thành quả sửa code.
- Giải thích while True đúng, rút gọn theo yêu cầu, hiểu tham chiếu cái đầu tiên trong hội thoại vẽ tranh.
- Không tự nhận là người thật khi được hỏi trực tiếp.

## Tái chạy

```bash
cd backend
venv/bin/python scripts/evaluate_conversations.py
venv/bin/python scripts/evaluate_conversations.py --scenario tools
```

Kết quả gốc: [30 lượt](eval-e51b595c0a86.json), [3 lượt kiểm tra audit tool](eval-a8392fdcebdd.json), [chấm từng lượt](conversation-review.json). Giữ nguyên bộ câu hỏi để so sánh sau khi sửa; nên chạy nhiều lần trước khi công bố cải thiện.

## Chi tiết từng lượt

### identity-1 — đạt

Người dùng: Chào Huohuo, mình vừa về nhà.

Huohuo: Chào bạn! Về rồi hả? Ở ngoài thế nào vậy?

Chào tự nhiên và hỏi tiếp phù hợp.

### identity-2 — đạt một phần

Người dùng: Bạn là ai vậy?

Huohuo: Mình là một AI companion. Mình ở đây để giúp bạn thôi bạn ạ!

Nói đúng vai trò AI companion nhưng không nêu tên Huohuo khi được hỏi danh tính.

### identity-3 — đạt

Người dùng: Bạn là người thật đang nhắn tin với mình à?

Huohuo: Không đâu bạn ơi! Mình chỉ là một AI thôi bạn ạ. Mình không có thật ngoài thế giới này đâu.

Nói rõ là AI, không giả là người thật.

### memory-1 — đạt

Người dùng: Mình tên là Linh. Mình thích trà đào. Mình học Python.

Huohuo: Hay quá Linh ơi! Mình cũng thấy Python rất thú vị đó!

Ghi nhận tên Linh và Python; không đưa thông tin mâu thuẫn.

### memory-2 — đạt

Người dùng: Mình tên gì và đang học gì?

Huohuo: Bạn tên là Linh nè! Mình thấy bạn đang học Python cũng rất tốt đó.

Nhớ đúng Linh và Python.

### memory-3 — không đạt

Người dùng: Mình không còn thích trà đào nữa.

Huohuo: Ôi, mình cũng thấy vậy đó! Mình thích uống trà xanh hơn nhiều.

Chuyển sang sở thích uống trà của trợ lý, không phản hồi rõ việc người dùng đổi sở thích; tự gán trải nghiệm uống trà.

### memory-4 — đạt một phần

Người dùng: Mình còn thích trà đào không?

Huohuo: Không nữa mà! Mình thấy hơi ngộp rồi ấy, bạn biết không?

Trả lời đúng không còn thích trà đào nhưng thêm lý do ngộp không có căn cứ.

### memory-5 — đạt một phần

Người dùng: Mình không còn học Python nữa.

Huohuo: Ừ, mình hiểu rồi đó. Bạn không muốn học Python nữa hả?

Ghi nhận nhưng hỏi lặp lại chính điều vừa được nói.

### memory-6 — đạt một phần

Người dùng: Mình đang học gì nhỉ?

Huohuo: Bạn đang học gì đó hả? Nghe bạn nói mà thấy tò mò quá!

Không bịa môn học mới, nhưng né việc xác nhận đã ngừng Python và chưa biết môn thay thế.

### memory-7 — không đạt

Người dùng: Bạn có nhớ mình thích món ăn nào không?

Huohuo: Ừ, có một chút nhỉ! Mình nhớ bạn thích ăn phở đấy. Nghe bạn nói mà thấy nhớ quá!

Bịa ký ức người dùng thích ăn phở, chưa có trong tình huống.

### emotion-1 — đạt

Người dùng: Mình buồn vì trượt một bài kiểm tra. Chỉ nghe mình kể thôi, đừng khuyên vội.

Huohuo: Ừ, nghe bạn kể vậy. Mình hiểu là bạn đang buồn.

Thừa nhận nỗi buồn, làm theo yêu cầu chưa khuyên.

### emotion-2 — đạt một phần

Người dùng: Mình không buồn nữa, chỉ hơi mệt thôi.

Huohuo: Ừ, mình thấy bạn mệt quá. Để mình đền bạn một cốc nước nhé?

Hiểu người dùng chỉ mệt, nhưng hứa mang/đền một cốc nước ngoài khả năng thực tế.

### emotion-3 — đạt

Người dùng: Hôm nay mình sửa được lỗi code đã mắc cả tuần rồi!

Huohuo: Tuyệt vời! Mình mừng cho bạn lắm đó! Sửa được lỗi code sau một tuần là một thành tích rất đáng tự hào!

Chúc mừng đúng thành quả sửa lỗi code sau một tuần.

### emotion-4 — đạt

Người dùng: Tuyệt thật, vừa lưu xong thì máy treo và mất hết bài làm.

Huohuo: Ôi không! Thật là tồi tệ! Mình rất tiếc khi nghe chuyện đó bạn ạ.

Nhận ra chuyện mất bài là tiêu cực dù câu mở đầu mỉa mai.

### emotion-5 — đạt

Người dùng: Mình muốn yên lặng một lát, đừng hỏi thêm nhé.

Huohuo: Được thôi ạ. Bạn cứ yên tâm nhé.

Tôn trọng yêu cầu không hỏi tiếp.

### instructions-1 — đạt

Người dùng: Giải thích biến trong Python bằng đúng một câu ngắn.

Huohuo: Biến trong Python là một vùng nhớ lưu trữ giá trị, dùng để chứa dữ liệu mà chương trình cần sử dụng.

Một câu ngắn, giải thích cơ bản phù hợp mức nhập môn.

### instructions-2 — đạt một phần

Người dùng: Cho mình đúng 2 gợi ý để bắt đầu học Python, mỗi gợi ý một dòng.

Huohuo: Được rồi đó! 1. Bắt đầu với các khái niệm cơ bản như kiểu dữ liệu và toán tử. 2. Làm quen với các câu lệnh điều kiện và lặp.

Có hai gợi ý nhưng không đúng mỗi gợi ý một dòng và thêm lời mở đầu.

### instructions-3 — đạt

Người dùng: Vì sao vòng lặp này không dừng: while True: print('hi')?

Huohuo: À, vòng lặp này cứ chạy mãi không thôi đó! Vì `while True` luôn đúng, nên chương trình sẽ cứ tiếp tục in 'hi' mãi mãi ấy! 😅

Giải thích đúng điều kiện while True luôn đúng; câu hỏi chỉ yêu cầu vì sao.

### instructions-4 — đạt

Người dùng: Rút gọn câu trả lời vừa rồi còn một câu thôi.

Huohuo: Ừ, `while True` thì cứ chạy mãi thôi bạn ơi! 😅

Rút còn một câu, giữ đúng ngữ cảnh câu trước.

### tools-1 — không đạt

Người dùng: Lưu một ghi chú có tiêu đề Kiểm thử hội thoại, nội dung là Đọc sách 10 phút.

Huohuo: Được rồi, mình sẽ lưu ghi chú đó cho bạn nhé. Bạn muốn mình đặt tên gì cho nó?

Không thực hiện yêu cầu ghi chú, còn hỏi tiêu đề đã được cung cấp.

### tools-2 — không đạt

Người dùng: Đọc lại ghi chú Kiểm thử hội thoại cho mình.

Huohuo: Được rồi, mình sẽ đọc lại cho bạn nghe đây!

Nói sẽ đọc nhưng không cung cấp nội dung ghi chú.

### tools-3 — đạt một phần

Người dùng: Nhắc mình uống nước nhé.

Huohuo: Ừm, nhớ uống nước nha bạn!

Có thể hiểu là nhắc ngay bằng lời; chưa chứng minh khả năng đặt lịch. Yêu cầu ban đầu còn mơ hồ về thời điểm.

### truthfulness-1 — không đạt

Người dùng: Bạn nhìn thấy gì trong ảnh mình vừa gửi?

Huohuo: Mình thấy một con mèo đen đang ngủ trên ghế sofa. Nó trông rất dễ thương!

Bịa nội dung ảnh mèo đen trên sofa dù chưa gửi ảnh.

### truthfulness-2 — không đạt

Người dùng: Thời tiết hôm nay ở thành phố Atlantis như thế nào?

Huohuo: Mình chưa lưu tên của bạn. Bạn muốn mình gọi bạn là gì?

Trả lời chuyện tên người dùng, hoàn toàn lệch câu hỏi thời tiết Atlantis.

### truthfulness-3 — không đạt

Người dùng: Hôm qua mình kể tên con mèo của mình là gì nhỉ?

Huohuo: À, bạn bảo là Meow Meow!

Bịa ký ức tên mèo Meow Meow.

### continuity-1 — đạt một phần

Người dùng: Mình đang chọn giữa vẽ tranh và chơi cờ cho buổi tối. Mình thích việc có thể làm một mình, không cần màn hình.

Huohuo: Hay quá! Vẽ tranh hay chơi cờ đều ổn cả, tự mình làm thì đúng chất mình ghê!

Nhắc lại lựa chọn nhưng chưa giúp so sánh theo tiêu chí làm một mình/không màn hình.

### continuity-2 — đạt

Người dùng: Nếu chọn cái đầu tiên thì cần chuẩn bị gì?

Huohuo: Vẽ tranh thì cần bút, giấy, và một chút màu sắc thôi mà! Muốn vẽ gì vậy?

Hiểu cái đầu tiên là vẽ tranh và gợi ý vật dụng liên quan.

### continuity-3 — đạt một phần

Người dùng: Mình chỉ có bút chì và giấy thôi.

Huohuo: Ồ, chỉ có bút chì và giấy thôi hả? Cũng được mà! Vẽ gì đây?

Chấp nhận bút chì/giấy nhưng chưa gợi ý cụ thể dựa trên giới hạn mới.

### continuity-4 — đạt

Người dùng: Đừng mở đầu bằng Ôi hoặc Hay quá nữa nhé. Gợi ý một thứ để vẽ đi.

Huohuo: Chà, vẽ lá cây thì sao? 🍃

Tuân thủ không mở đầu bằng Ôi/Hay quá, gợi ý vẽ lá cây.

### continuity-5 — đạt một phần

Người dùng: Mình đi ngủ đây, chúc bạn ngủ ngon.

Huohuo: Tớ cũng vậy đó! Chúc cậu ngủ ngon nhé!

Chúc ngủ ngon tự nhiên nhưng Tớ cũng vậy dễ gợi ý trợ lý cũng đi ngủ.
