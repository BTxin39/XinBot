"""Download the official Haru sample and Cubism Core for local evaluation."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1] / "pet"
BASE = "https://raw.githubusercontent.com/Live2D/CubismWebSamples/develop/"


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl.exe", "--ssl-revoke-best-effort", "-fL", "--retry", "2", "--max-time", "60", "-sS", url, "-o", str(target)], check=True)
    print(target.name)


def main():
    model_dir = ROOT / "live2d/haru"
    model_base = BASE + "Samples/Resources/Haru/"
    download(model_base + "Haru.model3.json", model_dir / "Haru.model3.json")
    refs = json.loads((model_dir / "Haru.model3.json").read_text())["FileReferences"]
    files = {refs["Moc"], *refs["Textures"]}
    for key in ("Physics", "Pose", "DisplayInfo", "UserData"):
        if refs.get(key):
            files.add(refs[key])
    files.update(item["File"] for item in refs.get("Expressions", []))
    for motions in refs.get("Motions", {}).values():
        for motion in motions:
            files.add(motion["File"])
            if motion.get("Sound"):
                files.add(motion["Sound"])
    for filename in sorted(files):
        download(model_base + filename, model_dir / filename)
    download(BASE + "LICENSE.md", model_dir / "LICENSE.md")
    download("https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js",
             ROOT / "vendor/live2dcubismcore.min.js")


if __name__ == "__main__":
    main()
