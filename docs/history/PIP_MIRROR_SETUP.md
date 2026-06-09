# مرآة pip/npm صينيّة (PyPI/npm محجوب أو بطيء)

## ما أُضيف
- **20 Dockerfile** (خدمات Python): ARG+ENV لـPIP_INDEX_URL + PIP_TRUSTED_HOST
  بمرآة تسينغهوا (TUNA) افتراضيّاً، قبل كلّ `RUN pip install`.
- **frontend/Dockerfile** (npm): ARG NPM_REGISTRY بمرآة npmmirror (علي بابا).
- **config/pip.conf**: للاستخدام خارج Docker (venv/المضيف، لينكس).
- **config/setup_pip_mirror.ps1**: سكربت ويندوز يضبط المرآة محلّيّاً (+BOM عربي).

## المرايا المستخدمة
| الأداة | المرآة الافتراضيّة |
|--------|--------------------|
| pip | https://pypi.tuna.tsinghua.edu.cn/simple (تسينغهوا) |
| npm | https://registry.npmmirror.com (علي بابا) |

## قابلة للتجاوز (لا تكسر البناء خارج اليمن)
كلّها ARG بقيمة افتراضيّة — تُتجاوز عند البناء:

    # مرآة علي بابا بدل تسينغهوا
    docker build \
      --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
      --build-arg PIP_TRUSTED_HOST=mirrors.aliyun.com -t svc .

    # العودة لـPyPI الرسمي (خارج اليمن)
    docker build --build-arg PIP_INDEX_URL=https://pypi.org/simple -t svc .

في docker-compose، مرّر عبر build.args:

    services:
      sahool-auth:
        build:
          context: .
          dockerfile: services/auth/Dockerfile
          args:
            PIP_INDEX_URL: https://pypi.tuna.tsinghua.edu.cn/simple

## مرايا بديلة موثوقة (لو تعطّلت الأولى)
- علي بابا: https://mirrors.aliyun.com/pypi/simple/  (mirrors.aliyun.com)
- USTC:     https://pypi.mirrors.ustc.edu.cn/simple/ (pypi.mirrors.ustc.edu.cn)
- تينسنت:   https://mirrors.cloud.tencent.com/pypi/simple/

## على المضيف (بلا Docker)
لينكس:   نسخ config/pip.conf → ~/.config/pip/pip.conf
ويندوز:  شغّل config/setup_pip_mirror.ps1 (يكتب %APPDATA%\pip\pip.ini)

## ملاحظة صدق
- لم أتمكّن من اختبار البناء فعليّاً (Docker + الشبكة محظوران في بيئتي).
  التحقّق بنيويّ: ترتيب ARG/ENV قبل pip، الصيغة صحيحة في 21 Dockerfile.
- اختبر البناء على جهازك: docker compose -f docker-compose.v9.yml build
- PIP_TRUSTED_HOST مضاف احتياطاً (لبروكسي الشركات)؛ تسينغهوا HTTPS صالح أصلاً.
