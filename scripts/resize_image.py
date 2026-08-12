import os

from PIL import Image


def resize_image(image_path, target_width=1280):
    try:
        if not os.path.exists(image_path):
            print(f"Error: {image_path} not found.")
            return

        img = Image.open(image_path)
        # Calculate height to preserve aspect ratio
        w_percent = target_width / float(img.size[0])
        h_size = int((float(img.size[1]) * float(w_percent)))

        # Resize
        img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)

        # Save
        img.save(image_path)
        print(f"Successfully resized {image_path} to width {target_width}.")
    except Exception as e:
        print(f"Error resizing image: {e}")


if __name__ == "__main__":
    # Path to the large image
    path = "/Users/ainunfajar/.gemini/antigravity/brain/b81885be-96f4-4e1d-b83a-597219007532/12_admin_sidak_1765962095622.png"
    resize_image(path)
