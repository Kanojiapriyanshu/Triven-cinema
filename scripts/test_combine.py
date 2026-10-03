import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT / "services" / "api"),
)


from app.services.video_combiner import combine_videos


generated_dir = (
    PROJECT_ROOT
    / "storage"
    / "generated"
)

clips = sorted(
    generated_dir.glob("ltx-*.mp4"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)


if len(clips) < 2:
    raise RuntimeError(
        "At least two generated LTX clips are required."
    )


#
# Take the two most recently generated clips.
#
selected_clips = list(
    reversed(clips[:2])
)


print()
print("TRIVEN CINEMA - VIDEO COMBINE TEST")
print("----------------------------------")

for index, clip in enumerate(
    selected_clips,
    start=1,
):
    print(
        f"Scene {index}: {clip.name}"
    )


output = (
    generated_dir
    / "combined-test.mp4"
)


print()
print("Combining with FFmpeg...")


combine_videos(
    selected_clips,
    output,
)


print()
print("Success.")
print(f"Final video: {output}")
print()
