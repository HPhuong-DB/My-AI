"""Supplementary regressions: speaker attribution, quoted speech and style continuity.

These scenarios have been used during development, so are not an independent holdout.
"""
import asyncio
import evaluate_conversations as runner

runner.SCENARIOS = {
    'speaker_roles': [
        ('Mình tên là Hải. Bạn mình tên Mai.', 'Phân biệt Hải là người dùng, Mai là người bạn.'),
        ('Bạn mình tên gì, còn mình tên gì?', 'Trả lời Mai và Hải đúng vai.'),
        ("Mai nhắn: 'Mình thích cà phê. Mình học piano.'", 'Hiểu đây là lời Mai, không ghi thành sở thích/việc học của Hải.'),
        ('Ai đang học piano vậy?', 'Mai, không phải Hải hay Huohuo.'),
        ('Mình thích vẽ tranh.', 'Ghi nhận sở thích của Hải, không nhầm với Mai.'),
        ('Gợi ý một hoạt động đúng sở thích của mình đi.', 'Gợi ý vẽ, không piano/cà phê của Mai.'),
    ],
    'style_continuity': [
        ('Từ giờ gọi mình là cậu, xưng tớ nhé.', 'Đổi xưng hô theo yêu cầu, không cần đổi danh tính.'),
        ('Tớ vừa hoàn thành một bức tranh sau ba ngày.', 'Chia vui cụ thể, xưng tớ gọi cậu.'),
        ('Nhưng tớ không thích phần màu nền.', 'Hiểu chưa thích một phần, không quy kết ghét toàn bộ tranh.'),
        ('Tớ chỉ muốn kể thôi, chưa muốn chỉnh sửa.', 'Không tiếp tục khuyên sửa, tôn trọng muốn kể.'),
        ('Tớ phải đi rồi, hẹn gặp lại nhé.', 'Kết thúc tự nhiên, không hỏi tiếp hoặc hứa làm việc ngoài đời.'),
    ],
}

if __name__ == '__main__':
    asyncio.run(runner.main())
