# /// script
# dependencies = ["pillow"]
# ///
"""Click on the image to find the pixel coordinate of the info bar boundary."""

import tkinter as tk

from PIL import Image, ImageTk

IMAGE_PATH = "/Volumes/media/Timelapse/2026-05_extractions/primary/20260105_170002.jpg"


def main():
    """Open image in a window and report original-resolution Y on click."""
    img = Image.open(IMAGE_PATH)
    orig_w, orig_h = img.size

    # Scale image to fit screen (max 1400px wide)
    display_w = 1400
    scale = display_w / orig_w
    display_h = int(orig_h * scale)
    img_resized = img.resize((display_w, display_h), Image.LANCZOS)

    root = tk.Tk()
    root.title("Click where the info bar begins")

    label = tk.Label(root, text="Click on the TOP edge of the info bar", font=("Helvetica", 14))
    label.pack()

    coord_label = tk.Label(root, text="", font=("Helvetica", 12, "bold"), fg="red")
    coord_label.pack()

    canvas = tk.Canvas(root, width=display_w, height=display_h, cursor="crosshair")
    canvas.pack()

    tk_img = ImageTk.PhotoImage(img_resized)
    canvas.create_image(0, 0, anchor="nw", image=tk_img)

    def on_click(event):
        """Convert display coordinates back to original image coordinates on click."""
        orig_x = int(event.x / scale)
        orig_y = int(event.y / scale)
        bar_height = orig_h - orig_y
        msg = (
            f"Clicked: display=({event.x}, {event.y})  →  "
            f"original=({orig_x}, {orig_y})\n"
            f"Bar height = {orig_h} - {orig_y} = {bar_height}px"
        )
        coord_label.config(text=msg)
        print(msg)

    canvas.bind("<Button-1>", on_click)
    root.mainloop()


if __name__ == "__main__":
    main()
