import os
import shutil

src_img = r"C:\Users\sdnse\.gemini\antigravity-ide\brain\edbcd223-a4d7-4761-ad2a-d74bffdcdcc5\test_image_1782368246535.png"
dst_img = r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2\scratch\test_image.png"

# Copy image
if os.path.exists(src_img):
    shutil.copy(src_img, dst_img)
    print("Test image copied successfully.")
else:
    print("Source image not found.")

# Create dummy PDF
dst_pdf = r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2\scratch\test_doc.pdf"
with open(dst_pdf, "wb") as f:
    f.write(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 24 Tf 100 700 Td (Dummy PDF File) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000216 00000 n\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n310\n%%EOF\n"
    )

print("Dummy PDF created successfully.")
