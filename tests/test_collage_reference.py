"""A character sheet / collage uploaded as a reference must not be replayed as the video."""
import unittest

from PIL import Image, ImageDraw

from app.schemas.elements import ResolvedElementBinding
from app.services.element_service import elements_for_scene, primary_subject_box


def turnaround_sheet() -> Image.Image:
    """One big close-up on the left and five thin full-body figures on a black background."""
    image = Image.new("RGB", (1280, 720), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 0, 465, 719), fill=(200, 150, 130))  # the close-up, full height
    for index in range(5):
        left = 490 + index * 155
        draw.rectangle((left, 80, left + 110, 640), fill=(150, 160, 210))
    return image


def binding(handle, mode="identity", apply_all=False, kind="character"):
    return ResolvedElementBinding(
        element_id=f"el_{handle}", version_id=f"ev_{handle}", handle=handle, name=handle.title(), type=kind,
        description="", reference_mode=mode, wardrobe_policy="prompt", strength=1.0, apply_to_all_scenes=apply_all,
        primary_asset_path=f"/x/{handle}.png", primary_asset_url="/x",
    )


class CollageDetectionTests(unittest.TestCase):
    def test_a_turnaround_sheet_is_cropped_to_the_big_close_up(self):
        left, top, right, bottom = primary_subject_box(turnaround_sheet())
        self.assertLessEqual(left, 25)
        self.assertGreaterEqual(right, 460)
        self.assertLessEqual(right, 485, "must not include the first full-body figure")
        self.assertLessEqual(top, 5)
        self.assertGreaterEqual(bottom, 715)

    def test_a_normal_portrait_on_a_plain_background_is_left_alone(self):
        image = Image.new("RGB", (800, 1000), (20, 20, 20))
        ImageDraw.Draw(image).ellipse((200, 150, 600, 650), fill=(210, 160, 140))
        self.assertIsNone(primary_subject_box(image))

    def test_a_busy_photo_is_left_alone(self):
        image = Image.effect_noise((800, 600), 64).convert("RGB")
        self.assertIsNone(primary_subject_box(image))

    def test_two_people_on_a_plain_background_are_not_treated_as_a_sheet(self):
        image = Image.new("RGB", (1000, 600), (10, 10, 10))
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 50, 400, 550), fill=(200, 150, 130))
        draw.rectangle((600, 50, 900, 550), fill=(150, 160, 210))
        self.assertIsNone(primary_subject_box(image))

    def test_tiny_images_are_ignored(self):
        self.assertIsNone(primary_subject_box(Image.new("RGB", (64, 64), (0, 0, 0))))


class ProductShotSceneTests(unittest.TestCase):
    def test_a_carried_character_does_not_leak_into_a_scene_that_opens_on_the_product(self):
        zoe = binding("zoe", apply_all=True)
        phone = binding("phone", mode="start_frame", kind="prop")
        scene_two = elements_for_scene("@phone slowly turns in soft light.", [zoe, phone])
        self.assertEqual([item.handle for item in scene_two], ["phone"])

    def test_the_carried_character_still_follows_a_normal_later_scene(self):
        zoe = binding("zoe", apply_all=True)
        phone = binding("phone", mode="start_frame", kind="prop")
        scene = elements_for_scene("She keeps talking to camera.", [zoe, phone])
        self.assertEqual([item.handle for item in scene], ["zoe"])

    def test_a_character_named_in_the_product_scene_is_kept(self):
        zoe = binding("zoe", apply_all=True)
        phone = binding("phone", mode="start_frame", kind="prop")
        scene = elements_for_scene("@zoe holds up @phone", [zoe, phone])
        self.assertEqual({item.handle for item in scene}, {"zoe", "phone"})


if __name__ == "__main__":
    unittest.main()
