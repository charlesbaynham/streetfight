// Turning a file somebody sent you into the same thing the camera produces.
//
// Latecomers are sent straight to their team rather than past the door, so the
// admin never gets to point a phone at them: the kit-check photo arrives over
// WhatsApp instead. That picture is whatever a stranger's phone produced -
// twelve megapixels, possibly rotated only by its EXIF tag - and everything
// downstream (admin_capture_reference_photo, the vision pipeline, the stored
// column) expects a modest JPEG data URL exactly like MyWebcam's.
//
// So the conversion happens here, in the browser: decode, rotate as the EXIF
// says, scale the long edge down to MAX_DIMENSION and re-encode as JPEG.

// The camera asks for 2048 wide, so an uploaded photo arrives at the pipeline
// the same size a photographed one does.
export const MAX_DIMENSION = 2048;

const JPEG_QUALITY = 0.92;

// A HEIC straight off an iPhone is the realistic failure: no browser but
// Safari will decode one, and the failure has to be said out loud rather than
// leaving the admin looking at a screen that did nothing.
export const UNREADABLE_MESSAGE =
  "That file could not be read as an image. If it came off an iPhone it may be " +
  "HEIC - ask for it again as a JPEG, or open it and re-save it as one.";

function decodeWithImageElement(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(UNREADABLE_MESSAGE));
    reader.onload = () => {
      const image = new Image();
      image.onerror = () => reject(new Error(UNREADABLE_MESSAGE));
      image.onload = () => resolve(image);
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

async function decode(file) {
  // createImageBitmap is the one path that honours the EXIF orientation tag,
  // which drawImage otherwise ignores - a portrait photo would reach the model
  // on its side, with the hat somewhere off to the left.
  if (typeof createImageBitmap === "function") {
    try {
      return await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch (e) {
      // Fall through: a browser that has it may still refuse the format, and
      // the <img> path may yet manage it.
    }
  }
  return decodeWithImageElement(file);
}

/** One picked file as a JPEG data URL, scaled to the camera's size.
 *
 * Rejects with a message fit to show the admin when nothing can decode it.
 */
export async function fileToPhotoDataURL(file) {
  const decoded = await decode(file);
  const width = decoded.width;
  const height = decoded.height;
  if (!width || !height) throw new Error(UNREADABLE_MESSAGE);

  const scale = Math.min(1, MAX_DIMENSION / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(decoded, 0, 0, canvas.width, canvas.height);
  if (decoded.close) decoded.close();

  const dataURL = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  // A canvas that drew nothing gives back "data:," which the backend rejects
  // as "the camera had no frame yet" - a baffling thing to read about a file.
  if (!dataURL || !dataURL.startsWith("data:image/"))
    throw new Error(UNREADABLE_MESSAGE);
  return dataURL;
}
