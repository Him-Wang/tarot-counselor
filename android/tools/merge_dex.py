"""把 d8 产出的 classes.dex 塞进 aapt2 打好的 base.apk（apk 里 dex 必须在根目录）。"""
import shutil
import sys
import zipfile

src, dex, dst = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.copyfile(src, dst)
with zipfile.ZipFile(dst, "a", zipfile.ZIP_DEFLATED) as z:
    z.write(dex, "classes.dex")
print("classes.dex appended ->", dst)
