import fitz
from PIL import Image, ImageCms
import io
import os

def convert_pdf_images_to_icc(input_pdf_path, output_pdf_path, target_icc_path):
    if not os.path.exists(target_icc_path):
        raise FileNotFoundError(f"Perfil no encontrado: {target_icc_path}")

    doc = fitz.open(input_pdf_path)
    target_profile = ImageCms.getProfile(target_icc_path)
    srgb_profile = ImageCms.createProfile("sRGB")

    for page_num in range(len(doc)):
        page = doc[page_num]
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image = Image.open(io.BytesIO(base_image["image"]))

            try:
                input_profile = srgb_profile
                if "icc_profile" in image.info:
                    input_profile = ImageCms.getProfile(io.BytesIO(image.info["icc_profile"]))

                output_mode = "CMYK" if "coated" in target_icc_path.lower() else "RGB"
                transform = ImageCms.buildTransform(input_profile, target_profile, image.mode, output_mode)
                converted_image = ImageCms.applyTransform(image, transform)

                buf = io.BytesIO()
                converted_image.save(buf, format="PNG")
                page.replace_image(xref, stream=buf.getvalue())
            except Exception as e:
                print(f"Aviso en página {page_num + 1}, xref {xref}: {e}")

    doc.save(output_pdf_path)
    doc.close()
