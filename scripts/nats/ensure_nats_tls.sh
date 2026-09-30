#!/bin/sh
# ensure_nats_tls.sh — مهمّةٌ لمرّةٍ واحدة قبل sahool-nats: مادّةُ TLS للوسيط حاضرةٌ وصالحة، أو فشلٌ مُسمّى.
#
# العطلُ المقيس (main@1cb6cd6c): منفذ العملاء 4222 نصٌّ صريح — كلماتُ مرور الخدمات في `CONNECT`
# ورسائلُ الأحداث كلُّها تعبر `sahool-internal` مقروءةً لكلّ من يلتقط حركتها. و`nats/nats.conf`
# صار يُلزِم TLS، فلا يُقلِع الوسيطُ بلا شهادة — وهذه المهمّةُ تضمنها أو تفشل باسمها.
#
# السياسةُ سياسةُ `scripts/nginx/ensure_gateway_tls.sh` نفسُها (fail-closed)، بملفّاتٍ مستقلّة:
#   * المادّةُ حاضرة ⇒ تُفحَص ولا تُمَسّ: تُقرأ · المفتاحُ يطابق · غيرُ منتهية · الشهادةُ تتسلسل إلى
#     ca.pem · اسمُ المضيف `sahool-nats` في SAN (العملاءُ يفحصون الاسم). وخارج التطوير تُرفَض
#     شهادةٌ ذاتيّةُ التوقيع للخادم، وتُرفَض مادّةُ التطوير المولَّدة (CA أو خادماً) — الإنتاجُ لا يعمل
#     بشهادةٍ ذاتيّةٍ بصمت، ولا بمادّة تطويرٍ نُسِيَت.
#   * غائبةٌ كلُّها و`SAHOOL_ENV` **صريحةٌ** غيرُ إنتاجيّة (development|dev|local|test) ⇒ يُولَّد CA
#     تطويرٍ وشهادةُ خادمٍ موقَّعةٌ منه (O=SAHOOL-DEV-SELF-SIGNED)، ثمّ **يُحذَف مفتاحُ CA**: لا حاجةَ
#     إليه بعد التوقيع، ووجودُه على القرص قدرةٌ على انتحال الوسيط لكلّ عميلٍ يثق بهذا CA.
#   * غائبةٌ وأيُّ قيمةٍ أخرى — production · staging · فارغة · خطأٌ إملائيّ ⇒ خروجٌ بـ1 ورسالةٌ تُسمّي
#     الملفّات والعلاجين، فلا يُقلِع الوسيط (depends_on: service_completed_successfully).
#   * بعضُها حاضرٌ وبعضُها غائب ⇒ فشلٌ في كلّ البيئات؛ لا يُكتَب فوق ما وضعه المشغِّل.
#
# التخطيط (مُركَّبٌ من ./nats/tls على المضيف):
#   server/server.pem · server/server-key.pem — يُركَّبان للوسيط وحدَه (/etc/nats/tls:ro).
#   ca/ca.pem + ca/<subject_hash>.0 — يُركَّبان للعملاء (/etc/sahool/nats-ca:ro) مع
#     `SSL_CERT_DIR` إليه: OpenSSL يبحث في مجلّد الثقة **باسم التجزئة**، وضبطُ المجلّد يُضيف CA
#     الوسيط إلى مخزن النظام (`SSL_CERT_FILE` يبقى افتراضيّاً) — لا يستبدله فيكسر HTTPS الخارجيّ.
#     ولا مفتاحَ خاصّاً في هذا المجلّد قطّ.
#
# لا يُلتزَم شيءٌ منها: `nats/tls/` و*.pem في .gitignore. `NATS_TLS_DIR` للاختبار وحدَه
# (tests_v9/test_nats_tls_init.py)؛ compose لا يضبطه.
set -eu

TLS_DIR="${NATS_TLS_DIR:-/etc/nats-tls}"
SRV_DIR="$TLS_DIR/server"
CA_DIR="$TLS_DIR/ca"
CERT="$SRV_DIR/server.pem"
KEY="$SRV_DIR/server-key.pem"
CA="$CA_DIR/ca.pem"
HOST_NAME="sahool-nats"
DEV_ORG="SAHOOL-DEV-SELF-SIGNED"
DEV_DAYS=365
ENV_RAW="${SAHOOL_ENV:-}"
ENV_NORM=$(printf '%s' "$ENV_RAW" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' | tr -d ' \t\r\n')

log() { printf 'nats-tls: %s\n' "$*"; }
fatal() {
    code=$1
    shift
    printf 'FATAL[nats-tls] %s: %s\n' "$code" "$*" >&2
    exit 1
}

command -v openssl >/dev/null 2>&1 ||
    fatal NATS_TLS_TOOLING_MISSING "openssl CLI is absent from the init image — cannot verify or generate TLS material"
[ -d "$TLS_DIR" ] ||
    fatal NATS_TLS_DIR_MISSING "$TLS_DIR is not a directory — mount ./nats/tls there (docker-compose.v9.yml)"

case "$ENV_NORM" in
    development | dev | local | test) DEV=1 ;;
    *) DEV=0 ;;
esac

subject_of() { openssl x509 -in "$1" -noout -subject -nameopt RFC2253 2>/dev/null | sed 's/^subject=//'; }
issuer_of() { openssl x509 -in "$1" -noout -issuer -nameopt RFC2253 2>/dev/null | sed 's/^issuer=//'; }
is_dev_material() {
    case ",$(subject_of "$1")," in
        *",O=$DEV_ORG,"*) return 0 ;;
    esac
    return 1
}

generate_dev_material() {
    mkdir -p "$SRV_DIR" "$CA_DIR" ||
        fatal NATS_TLS_GENERATION_FAILED "cannot create $SRV_DIR and $CA_DIR (is the mount writable?)"
    work=$(mktemp -d "$TLS_DIR/.nats-tls.XXXXXX") ||
        fatal NATS_TLS_GENERATION_FAILED "cannot create a work directory inside $TLS_DIR (is the mount writable?)"
    # إعدادٌ صريح لا ملفُّ openssl.cnf في الصورة: التوليدُ لا يتبدّل بتبدّل توزيعة الصورة.
    cat >"$work/ca.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
x509_extensions = v3
[dn]
O = $DEV_ORG
CN = SAHOOL development NATS CA
[v3]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
    cat >"$work/server.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
O = $DEV_ORG
CN = $HOST_NAME
[v3]
subjectAltName = DNS:$HOST_NAME,DNS:localhost,IP:127.0.0.1
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF
    old_umask=$(umask)
    umask 077
    if ! {
        openssl req -x509 -config "$work/ca.cnf" -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
            -nodes -days "$DEV_DAYS" -keyout "$work/ca-key.pem" -out "$work/ca.pem" &&
            openssl req -new -config "$work/server.cnf" -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
                -nodes -keyout "$work/server-key.pem" -out "$work/server.csr" &&
            openssl x509 -req -in "$work/server.csr" -CA "$work/ca.pem" -CAkey "$work/ca-key.pem" \
                -set_serial "0x$(openssl rand -hex 16)" -days "$DEV_DAYS" \
                -extfile "$work/server.cnf" -extensions v3 -out "$work/server.pem"
    } >"$work/openssl.log" 2>&1; then
        detail=$(tr '\n' ' ' <"$work/openssl.log")
        rm -rf "$work"
        fatal NATS_TLS_GENERATION_FAILED "openssl failed: $detail"
    fi
    umask "$old_umask"
    # مفتاحُ CA لا يغادر مجلّدَ العمل: التوقيعُ تمّ، وبقاؤه قدرةٌ على انتحال الوسيط.
    rm -f "$work/ca-key.pem" "$work/server.csr"
    chmod 600 "$work/server-key.pem"
    chmod 644 "$work/server.pem" "$work/ca.pem"
    # المفتاحُ أوّلاً ثمّ الشهادة ثمّ CA: انقطاعٌ بينها يُبقي مادّةً ناقصةً تُرفَض صراحةً لا مختلطة.
    mv -f "$work/server-key.pem" "$KEY"
    mv -f "$work/server.pem" "$CERT"
    mv -f "$work/ca.pem" "$CA"
    rm -rf "$work"
    log "generated a DEVELOPMENT CA + server certificate (SAHOOL_ENV=$ENV_RAW, SAN=DNS:$HOST_NAME, ${DEV_DAYS}d); the CA key was discarded"
}

present=0
for f in "$CERT" "$KEY" "$CA"; do
    [ -e "$f" ] && present=$((present + 1))
done

if [ "$present" = 0 ]; then
    if [ "$DEV" = 1 ]; then
        generate_dev_material
    else
        fatal NATS_TLS_MISSING "no broker TLS material at $CERT + $KEY + $CA (host: ./nats/tls/) and SAHOOL_ENV='$ENV_RAW' is not an explicit development environment (development|dev|local|test). Production never mints a self-signed broker certificate: place server/server.pem (issued for DNS:$HOST_NAME), server/server-key.pem and ca/ca.pem (its issuing CA) in nats/tls/ — or, for a local machine only, set SAHOOL_ENV=development and development material is generated."
    fi
elif [ "$present" != 3 ]; then
    fatal NATS_TLS_PARTIAL "only $present of server.pem/server-key.pem/ca.pem exist under $TLS_DIR — refusing to overwrite or guess; provide all three (or remove all three in development to regenerate)"
fi

for f in "$CERT" "$CA"; do
    openssl x509 -in "$f" -noout 2>/dev/null ||
        fatal NATS_TLS_UNREADABLE "$f is not a readable PEM certificate"
done
[ "$(grep -c 'BEGIN CERTIFICATE' "$CA")" = 1 ] ||
    fatal NATS_TLS_CA_BUNDLE_UNSUPPORTED "$CA must hold exactly one CA certificate (the broker's issuer) — the client trust directory is indexed by one subject hash"

expired=""
for f in "$CERT" "$CA"; do
    openssl x509 -in "$f" -noout -checkend 0 >/dev/null 2>&1 || expired="$expired $f"
done
if [ -n "$expired" ]; then
    if [ "$DEV" = 1 ] && is_dev_material "$CERT" && is_dev_material "$CA"; then
        log "the generated development material expired —$expired — regenerating it"
        rm -f "$CERT" "$KEY" "$CA"
        generate_dev_material
    else
        fatal NATS_TLS_EXPIRED "expired:$expired — renew it"
    fi
fi

openssl pkey -in "$KEY" -passin pass: -noout >/dev/null 2>&1 ||
    fatal NATS_TLS_UNREADABLE "$KEY is not a readable unencrypted private key (nats-server cannot prompt for a passphrase)"
cert_pub=$(openssl x509 -in "$CERT" -noout -pubkey 2>/dev/null)
key_pub=$(openssl pkey -in "$KEY" -passin pass: -pubout 2>/dev/null)
[ -n "$cert_pub" ] && [ "$cert_pub" = "$key_pub" ] ||
    fatal NATS_TLS_KEY_MISMATCH "$KEY does not match the certificate in $CERT"

openssl verify -CAfile "$CA" "$CERT" >/dev/null 2>&1 ||
    fatal NATS_TLS_CHAIN_INVALID "$CERT does not chain to $CA — clients trust exactly that CA and would refuse the broker"

san=$(openssl x509 -in "$CERT" -noout -ext subjectAltName 2>/dev/null | tail -n +2 | tr ',' '\n' | tr -d ' \t')
printf '%s\n' "$san" | grep -qx "DNS:$HOST_NAME" ||
    fatal NATS_TLS_NAME_MISMATCH "$CERT has no subjectAltName DNS:$HOST_NAME — every client connects to tls://…@$HOST_NAME:4222 and checks the name"

subject=$(subject_of "$CERT")
issuer=$(issuer_of "$CERT")
if [ "$DEV" = 0 ]; then
    if is_dev_material "$CERT" || is_dev_material "$CA"; then
        fatal NATS_TLS_DEV_MATERIAL_OUTSIDE_DEV "refusing the auto-generated development material (O=$DEV_ORG) left in nats/tls/ with SAHOOL_ENV='$ENV_RAW' — install a certificate issued by your CA"
    fi
    [ "$subject" != "$issuer" ] ||
        fatal NATS_TLS_SELF_SIGNED_OUTSIDE_DEV "refusing a self-signed broker certificate with SAHOOL_ENV='$ENV_RAW' (subject == issuer: $subject) — install a certificate issued by a CA and put that CA in ca/ca.pem"
fi

# فهرسُ الثقة للعملاء: `<subject_hash>.0` هو ما يبحث عنه OpenSSL في `SSL_CERT_DIR`. ويُحذَف كلُّ
# فهرسٍ آخر: CA قديمٌ بعد تدويرٍ يبقى موثوقاً ما بقي ملفُّه، وهو ما يُراد إسقاطُه بالتدوير.
hash=$(openssl x509 -in "$CA" -noout -hash 2>/dev/null) ||
    fatal NATS_TLS_UNREADABLE "cannot compute the subject hash of $CA"
for old in "$CA_DIR"/*.[0-9]; do
    [ -e "$old" ] || continue
    [ "$old" = "$CA_DIR/$hash.0" ] || rm -f "$old"
done
cmp -s "$CA" "$CA_DIR/$hash.0" 2>/dev/null || cp "$CA" "$CA_DIR/$hash.0"
chmod 644 "$CA_DIR/$hash.0"

log "ok ($([ "$DEV" = 1 ] && echo development || echo "non-development: $ENV_RAW")): subject=[$subject] issuer=[$issuer] $(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null) trust-index=$hash.0"
