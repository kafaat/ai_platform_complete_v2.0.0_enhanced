"""اختبارات وحدة لـobject_store — لا تتطلّب S3 حيّاً.

تُثبت: (١) تحويل URI إلى مسار GDAL (s3://→/vsis3/، file://→مسار، خام كما هو)؛
(٢) عند عدم ضبط S3: enabled()=False وupload_cog يتدهور إلى file://؛
(٣) exists_locally يؤجّل s3:// (True) ويفحص file:// على القرص.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# تأكّد أنّ بيئة S3 غير مضبوطة قبل استيراد الموديول (كي يكون enabled()=False).
for _k in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
    os.environ.pop(_k, None)

import object_store  # noqa: E402


def test_to_gdal_path():
    assert object_store.to_gdal_path("s3://b/k") == "/vsis3/b/k"
    assert object_store.to_gdal_path("file:///tmp/x") == "/tmp/x"
    assert object_store.to_gdal_path("/tmp/y") == "/tmp/y"
    print("✓ to_gdal_path: s3://→/vsis3/، file://→مسار، خام كما هو")


def test_disabled_behavior():
    assert object_store.enabled() is False, "يجب أن يكون S3 معطّلاً دون ضبط S3_*"
    assert object_store.upload_cog("/tmp/z.tif", "k") == "file:///tmp/z.tif", (
        "عند التعطيل يجب أن يُرجِع upload_cog مسار file:// كما هو"
    )
    print("✓ معطّل: enabled()=False وupload_cog يتدهور إلى file:///tmp/z.tif")


def test_exists_locally():
    assert object_store.exists_locally("s3://b/k") is True, "s3:// يُؤجَّل (True)"
    assert object_store.exists_locally("file:///nope") is False, "file:// مفقود → False"
    print("✓ exists_locally: s3://→True (مؤجَّل)، file:///nope→False")


if __name__ == "__main__":
    test_to_gdal_path()
    test_disabled_behavior()
    test_exists_locally()
    print("ALL OBJECT_STORE ASSERTIONS PASSED")
