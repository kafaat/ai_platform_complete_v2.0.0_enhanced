#!/bin/sh
# ensure_gateway_tls.sh — بوّابةٌ لمرّةٍ واحدة قبل sahool-nginx: زوجُ TLS حاضرٌ وصالح، أو فشلٌ مُسمّى.
#
# العطلُ المقيس (تدقيقُ التشغيل الحيّ 2026-09-29، docker-compose.v9.yml على آلةٍ نظيفة):
# nginx.v9.conf يُعلن `listen 443 ssl` بـ/etc/nginx/ssl/{fullchain,privkey}.pem، والمستودعُ بلا
# nginx/ssl ولا مولِّد. فأنشأ Docker مجلّدَ التركيب فارغاً، ومات nginx في كلّ إقلاعٍ على
# `cannot load certificate ".../fullchain.pem"` وأُعيد تشغيلُه 31 مرّة — البوّابةُ العامّة كلُّها ساقطة.
#
# القاعدة (fail-closed):
#   * الزوجُ حاضر ⇒ يُفحَص (يُقرأ · المفتاحُ يطابق الشهادة · غيرُ منتهية) ولا يُمَسّ. وخارج التطوير
#     تُرفَض الشهادةُ الذاتيّةُ التوقيع — الإنتاجُ لا يخدم شهادةً ذاتيّةً بصمت، ولا شهادةَ تطويرٍ نُسِيَت.
#   * الزوجُ غائب و`SAHOOL_ENV` **صريحةٌ** غيرُ إنتاجيّة (development|dev|local|test) ⇒ تُولَّد شهادةُ
#     تطويرٍ ذاتيّة (O=SAHOOL-DEV-SELF-SIGNED) في المجلّد المُركَّب وحدَه.
#   * الزوجُ غائب وأيُّ قيمةٍ أخرى — production · staging · فارغةٌ · خطأٌ إملائيّ ⇒ خروجٌ بـ1 ورسالةٌ
#     تُسمّي الملفَّين والعلاجين، فلا يُقلِع nginx (depends_on: service_completed_successfully).
#   * نصفُ زوج ⇒ فشلٌ في كلّ البيئات؛ لا يُكتَب فوق ملفٍّ وضعه المشغِّل.
#
# لا يُلتزَم أيُّ مفتاح: nginx/ssl/ و*.pem في .gitignore، والتوليدُ يقع وقتَ التشغيل على المضيف.
# `GATEWAY_TLS_DIR` للاختبار وحدَه (tests_v9/test_gateway_tls_init.py)؛ compose لا يضبطه.
set -eu

TLS_DIR="${GATEWAY_TLS_DIR:-/etc/nginx/ssl}"
CERT="$TLS_DIR/fullchain.pem"
KEY="$TLS_DIR/privkey.pem"
DEV_ORG="SAHOOL-DEV-SELF-SIGNED"
DEV_DAYS=365
ENV_RAW="${SAHOOL_ENV:-}"
ENV_NORM=$(printf '%s' "$ENV_RAW" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' | tr -d ' \t\r\n')
DOMAIN_NAME="${DOMAIN:-localhost}"

log() { printf 'gateway-tls: %s\n' "$*"; }
fatal() {
    code=$1
    shift
    printf 'FATAL[gateway-tls] %s: %s\n' "$code" "$*" >&2
    exit 1
}

command -v openssl >/dev/null 2>&1 ||
    fatal GATEWAY_TLS_TOOLING_MISSING "openssl CLI is absent from the init image — cannot verify or generate TLS material"
[ -d "$TLS_DIR" ] ||
    fatal GATEWAY_TLS_DIR_MISSING "$TLS_DIR is not a directory — mount ./nginx/ssl there (docker-compose.v9.yml)"

case "$ENV_NORM" in
    development | dev | local | test) DEV=1 ;;
    *) DEV=0 ;;
esac

subject_of() { openssl x509 -in "$1" -noout -subject -nameopt RFC2253 2>/dev/null | sed 's/^subject=//'; }
issuer_of() { openssl x509 -in "$1" -noout -issuer -nameopt RFC2253 2>/dev/null | sed 's/^issuer=//'; }

generate_dev_pair() {
    case "$DOMAIN_NAME" in
        '' | .* | -* | *[!A-Za-z0-9.-]*)
            fatal GATEWAY_TLS_BAD_DOMAIN "DOMAIN='$DOMAIN_NAME' is not a hostname/IPv4 — refusing to mint a certificate for it"
            ;;
    esac
    case "$DOMAIN_NAME" in
        *[!0-9.]*) san="DNS:$DOMAIN_NAME" ;;
        *) san="IP:$DOMAIN_NAME" ;;
    esac
    [ "$DOMAIN_NAME" = localhost ] || san="$san,DNS:localhost"
    [ "$DOMAIN_NAME" = 127.0.0.1 ] || san="$san,IP:127.0.0.1"

    work=$(mktemp -d "$TLS_DIR/.gateway-tls.XXXXXX") ||
        fatal GATEWAY_TLS_GENERATION_FAILED "cannot create a work directory inside $TLS_DIR (is the mount writable?)"
    # إعدادٌ صريح لا ملفُّ openssl.cnf في الصورة: التوليدُ لا يتبدّل بتبدّل توزيعة الصورة.
    cat >"$work/req.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
x509_extensions = v3
[dn]
O = $DEV_ORG
CN = $DOMAIN_NAME
[v3]
subjectAltName = $san
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
EOF
    old_umask=$(umask)
    umask 077
    if ! openssl req -x509 -config "$work/req.cnf" -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
        -nodes -days "$DEV_DAYS" -keyout "$work/privkey.pem" -out "$work/fullchain.pem" \
        >"$work/openssl.log" 2>&1; then
        detail=$(tr '\n' ' ' <"$work/openssl.log")
        rm -rf "$work"
        fatal GATEWAY_TLS_GENERATION_FAILED "openssl req failed: $detail"
    fi
    umask "$old_umask"
    chmod 600 "$work/privkey.pem"
    chmod 644 "$work/fullchain.pem"
    # المفتاحُ أوّلاً ثمّ الشهادة: إن انقطع التشغيلُ بينهما بقي نصفُ زوجٍ يُرفَض صراحةً لا زوجٌ مختلط.
    mv -f "$work/privkey.pem" "$KEY"
    mv -f "$work/fullchain.pem" "$CERT"
    rm -rf "$work"
    log "generated a self-signed DEVELOPMENT certificate (SAHOOL_ENV=$ENV_RAW, SAN=$san, ${DEV_DAYS}d) at $CERT"
}

have_cert=0
have_key=0
[ -e "$CERT" ] && have_cert=1
[ -e "$KEY" ] && have_key=1

if [ "$have_cert" = 0 ] && [ "$have_key" = 0 ]; then
    if [ "$DEV" = 1 ]; then
        generate_dev_pair
    else
        fatal GATEWAY_TLS_MISSING "no TLS pair at $CERT + $KEY (host: ./nginx/ssl/) and SAHOOL_ENV='$ENV_RAW' is not an explicit development environment (development|dev|local|test). Production never mints a self-signed certificate: place the real fullchain.pem and privkey.pem in nginx/ssl/ — or, for a local machine only, set SAHOOL_ENV=development and a development certificate is generated."
    fi
elif [ "$have_cert" != "$have_key" ]; then
    fatal GATEWAY_TLS_PARTIAL "only one of fullchain.pem/privkey.pem exists in $TLS_DIR — refusing to overwrite or guess; provide both (or remove both in development to regenerate)"
fi

openssl x509 -in "$CERT" -noout 2>/dev/null ||
    fatal GATEWAY_TLS_UNREADABLE "$CERT is not a readable PEM certificate"

subject=$(subject_of "$CERT")
issuer=$(issuer_of "$CERT")
ours=0
case ",$subject," in
    *",O=$DEV_ORG,"*) ours=1 ;;
esac

if ! openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null 2>&1; then
    if [ "$DEV" = 1 ] && [ "$ours" = 1 ]; then
        log "the generated development certificate expired — regenerating it"
        rm -f "$CERT" "$KEY"
        generate_dev_pair
        subject=$(subject_of "$CERT")
        issuer=$(issuer_of "$CERT")
    else
        fatal GATEWAY_TLS_EXPIRED "$CERT has expired (notAfter: $(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')) — renew it"
    fi
fi

openssl pkey -in "$KEY" -passin pass: -noout >/dev/null 2>&1 ||
    fatal GATEWAY_TLS_UNREADABLE "$KEY is not a readable unencrypted private key (nginx cannot prompt for a passphrase)"
cert_pub=$(openssl x509 -in "$CERT" -noout -pubkey 2>/dev/null)
key_pub=$(openssl pkey -in "$KEY" -passin pass: -pubout 2>/dev/null)
[ -n "$cert_pub" ] && [ "$cert_pub" = "$key_pub" ] ||
    fatal GATEWAY_TLS_KEY_MISMATCH "$KEY does not match the certificate in $CERT"

if [ "$DEV" = 0 ] && [ "$subject" = "$issuer" ]; then
    if [ "$ours" = 1 ]; then
        why="it is the auto-generated development certificate (O=$DEV_ORG) left in nginx/ssl/"
    else
        why="it is self-signed (subject == issuer: $subject)"
    fi
    fatal GATEWAY_TLS_SELF_SIGNED_OUTSIDE_DEV "refusing to serve $CERT with SAHOOL_ENV='$ENV_RAW': $why. Install a certificate issued by a CA."
fi

log "ok ($([ "$DEV" = 1 ] && echo development || echo "non-development: $ENV_RAW")): subject=[$subject] issuer=[$issuer] $(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null)"
