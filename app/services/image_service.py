from fastapi import UploadFile


class ImageService:
    async def analyze_image(self, image: UploadFile | None) -> str:
        if image is None:
            return "No image was uploaded."

        # Placeholder for Gemini Vision integration.
        return (
            f"Received image '{image.filename}'. "
            "Vision analysis can be connected here with Gemini multimodal prompts."
        )
