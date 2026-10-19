# Third-party components

| Component | Version / source | License |
|---|---|---|
| Bootstrap | 5.3.8, https://github.com/twbs/bootstrap | MIT, `static/vendor/BOOTSTRAP-LICENSE.txt` |
| Chart.js | 4.5.1, https://github.com/chartjs/Chart.js | MIT, `static/vendor/CHARTJS-LICENSE.md` |
| Noto Sans Thai | System-provided Noto Sans Thai, https://github.com/notofonts/thai | SIL Open Font License, `static/vendor/FONT-LICENSE.txt` |
| llama.cpp | `31288c9c66e59377f7788d920678a565bb89dd37`, https://github.com/ggml-org/llama.cpp | MIT, license in downloaded source |
| Qwen2.5-0.5B-Instruct GGUF | https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF | Apache 2.0 per official model card; retain the model's license if redistributing |
| Tesseract / tessdata_fast | https://github.com/tesseract-ocr/tesseract / https://github.com/tesseract-ocr/tessdata_fast | Apache 2.0 |

Python dependencies and versions appear in requirements files. The model binary is excluded from Git and distributable source archives. Download it using the checksum-verifying script. No external UI assets are fetched at runtime.
