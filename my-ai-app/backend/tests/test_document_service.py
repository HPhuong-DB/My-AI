import unittest

from services.document_service import chunk_text, extract_document


class DocumentServiceTests(unittest.TestCase):
    def test_extracts_text_markdown_and_metadata(self):
        result = extract_document("# Tiêu đề\n\nNội dung".encode(), "note.md")
        self.assertEqual(result.document_type, "md")
        self.assertEqual(result.char_count, len("# Tiêu đề\n\nNội dung"))
        self.assertIn("Tiêu đề", result.text)

    def test_extracts_csv_as_readable_text(self):
        result = extract_document("name,score\nAn,10".encode(), "scores.csv")
        self.assertIn("name | score", result.text)
        self.assertIn("An | 10", result.text)

    def test_extracts_docx_paragraphs_without_external_docx_runtime(self):
        import io
        import zipfile

        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Xin chào</w:t></w:r></w:p></w:body></w:document>'
        ).encode()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", xml)

        result = extract_document(buffer.getvalue(), "hello.docx")
        self.assertEqual(result.text, "Xin chào")

    def test_rejects_unsupported_document(self):
        with self.assertRaises(ValueError):
            extract_document(b"data", "secret.exe")

    def test_chunks_text(self):
        self.assertEqual(chunk_text("abcdef", chunk_size=2), ["ab", "cd", "ef"])


if __name__ == "__main__":
    unittest.main()
