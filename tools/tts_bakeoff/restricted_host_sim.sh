#!/bin/sh
# محاكاةُ مضيفٍ مقيَّد (كمضيف المالك في مراجعة v12) على مضيفٍ يسمح بها — بشروطٍ حقيقيّة لا بأعلام:
#   cgroup v1 للقراءة فقط (EROFS حقيقيّ عبر ربطٍ للقراءة فقط في mount namespace خاصّ)،
#   ثمّ إسقاطُ كلّ الصلاحيّات + no_new_privs ⇒ CapEff=0، فيُرفض unshare وbwrap (EPERM).
# يتطلّب root بصلاحيّات (لإنشاء المحاكاة نفسها). الاستعمال: sh restricted_host_sim.sh python3 selftest.py
set -e
exec unshare -m -- sh -c '
mount --make-rprivate /
for c in memory cpu; do mount --bind /sys/fs/cgroup/$c /sys/fs/cgroup/$c && mount -o remount,bind,ro /sys/fs/cgroup/$c; done
exec setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs -- "$@"' sh "$@"
