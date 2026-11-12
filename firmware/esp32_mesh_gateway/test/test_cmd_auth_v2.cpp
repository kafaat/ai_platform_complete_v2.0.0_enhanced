// Host test for cmd_auth_v2.h: g++ + OpenSSL, against the vectors the Python reference writes
// (cmd_auth_v2_vectors.json, gen_cmd_auth_v2_vectors.py). Build and run: `make -C <this dir>`.
//
// The JSON reader below is deliberately tiny (objects, arrays, strings without \u escapes
// beyond ASCII, unsigned integers, booleans, null) — enough for the generated file, no
// dependency to install on a build host.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "../cmd_auth_v2.h"

namespace {

struct J {
  enum T { NUL, BOOL, NUM, STR, ARR, OBJ } t = NUL;
  bool b = false;
  bool neg = false;
  uint64_t n = 0;
  std::string s;
  std::vector<std::shared_ptr<J>> a;
  std::map<std::string, std::shared_ptr<J>> o;
  const J* get(const std::string& k) const {
    auto it = o.find(k);
    return it == o.end() ? nullptr : it->second.get();
  }
};

struct Parser {
  const std::string& src;
  size_t i = 0;
  explicit Parser(const std::string& s) : src(s) {}
  void ws() {
    while (i < src.size() && (src[i] == ' ' || src[i] == '\n' || src[i] == '\r' || src[i] == '\t'))
      i++;
  }
  [[noreturn]] void fail(const char* what) {
    std::fprintf(stderr, "json: %s at %zu\n", what, i);
    std::exit(2);
  }
  std::string str() {
    if (src[i] != '"') fail("expected string");
    i++;
    std::string out;
    while (i < src.size() && src[i] != '"') {
      if (src[i] == '\\') {
        i++;
        char c = src[i];
        if (c == 'n') out += '\n';
        else if (c == 't') out += '\t';
        else if (c == 'u') {  // \uXXXX: only used in the $comment; keep a placeholder
          i += 4;
          out += '?';
        } else out += c;
        i++;
      } else {
        out += src[i++];
      }
    }
    i++;
    return out;
  }
  std::shared_ptr<J> val() {
    ws();
    auto v = std::make_shared<J>();
    char c = src[i];
    if (c == '{') {
      v->t = J::OBJ;
      i++;
      ws();
      if (src[i] == '}') { i++; return v; }
      for (;;) {
        ws();
        std::string k = str();
        ws();
        if (src[i++] != ':') fail("expected :");
        v->o[k] = val();
        ws();
        if (src[i] == ',') { i++; continue; }
        if (src[i] == '}') { i++; return v; }
        fail("expected , or }");
      }
    }
    if (c == '[') {
      v->t = J::ARR;
      i++;
      ws();
      if (src[i] == ']') { i++; return v; }
      for (;;) {
        v->a.push_back(val());
        ws();
        if (src[i] == ',') { i++; continue; }
        if (src[i] == ']') { i++; return v; }
        fail("expected , or ]");
      }
    }
    if (c == '"') { v->t = J::STR; v->s = str(); return v; }
    if (src.compare(i, 4, "true") == 0) { v->t = J::BOOL; v->b = true; i += 4; return v; }
    if (src.compare(i, 5, "false") == 0) { v->t = J::BOOL; i += 5; return v; }
    if (src.compare(i, 4, "null") == 0) { i += 4; return v; }
    if (c == '-' || (c >= '0' && c <= '9')) {
      v->t = J::NUM;
      if (c == '-') { v->neg = true; i++; }
      while (i < src.size() && src[i] >= '0' && src[i] <= '9') v->n = v->n * 10 + (src[i++] - '0');
      if (i < src.size() && (src[i] == '.' || src[i] == 'e' || src[i] == 'E')) fail("float");
      return v;
    }
    fail("unexpected token");
  }
};

int failures = 0;
int checks = 0;

void expect_eq(const std::string& what, const std::string& got, const std::string& want) {
  checks++;
  if (got != want) {
    failures++;
    std::printf("FAIL %s\n  got:  %s\n  want: %s\n", what.c_str(), got.c_str(), want.c_str());
  }
}

const char* cstr(const J* v) { return (v && v->t == J::STR) ? v->s.c_str() : nullptr; }

bool uint_field(const J* v, uint64_t* out) {
  if (v == nullptr || v->t != J::NUM || v->neg) return false;
  *out = v->n;
  return true;
}

// Mirrors what the sketch extracts from the ArduinoJson document.
cmdauth::Command to_command(const J& m) {
  cmdauth::Command c{};
  const J* v = m.get("v");
  c.has_v = v && v->t == J::NUM && !v->neg;
  c.v = c.has_v ? (long)v->n : 0;
  c.id = cstr(m.get("id"));
  c.cmd = cstr(m.get("cmd"));
  c.tenant = cstr(m.get("tenant"));
  c.device = cstr(m.get("device"));
  c.field = cstr(m.get("field"));
  c.sig = cstr(m.get("sig"));
  bool ok = uint_field(m.get("iat"), &c.iat) && uint_field(m.get("exp"), &c.exp) &&
            uint_field(m.get("ctr"), &c.ctr);
  const J* p = m.get("payload");
  const J* d = (p && p->t == J::OBJ) ? p->get("duration_ms") : nullptr;
  if (d == nullptr) c.duration_ms = 0;
  else ok = ok && uint_field(d, &c.duration_ms);
  c.numbers_ok = ok;
  return c;
}

cmdauth::Config to_config(const J& s) {
  cmdauth::Config c{};
  std::snprintf(c.tenant, sizeof(c.tenant), "%s", cstr(s.get("tenant")));
  std::snprintf(c.device, sizeof(c.device), "%s", cstr(s.get("device")));
  std::snprintf(c.field, sizeof(c.field), "%s", cstr(s.get("field")));
  c.has_key = cmdauth::parse_key_hex(cstr(s.get("dk_hex")), c.key);
  c.last_ctr = s.get("last_ctr")->n;
  return c;
}

}  // namespace

int main(int argc, char** argv) {
  const char* path = argc > 1 ? argv[1] : "cmd_auth_v2_vectors.json";
  std::ifstream f(path);
  if (!f) {
    std::fprintf(stderr, "cannot open %s\n", path);
    return 2;
  }
  std::stringstream ss;
  ss << f.rdbuf();
  std::string text = ss.str();
  Parser p(text);
  auto root = p.val();

  const char* master = cstr(root->get("kdf_master"));
  for (auto& k : root->get("kdf")->a) {
    char hex[65];
    bool ok = cmdauth::derive_device_key_hex(master, cstr(k->get("tenant")), cstr(k->get("device")), hex);
    expect_eq(std::string("kdf ") + cstr(k->get("tenant")) + "/" + cstr(k->get("device")),
              ok ? hex : "<error>", cstr(k->get("dk_hex")));
  }

  int n_cmd = 0;
  for (auto& c : root->get("commands")->a) {
    n_cmd++;
    std::string name = cstr(c->get("name"));
    cmdauth::Config cfg = to_config(*c->get("state"));
    cmdauth::Command cmd = to_command(*c->get("msg"));
    // Signing string (when the Python reference could build one) must be byte-identical.
    const char* want_ss = cstr(c->get("signing_string"));
    if (want_ss != nullptr) {
      char buf[cmdauth::kMsgMax];
      cmdauth::build_command_string(buf, sizeof(buf), cmd.tenant, cmd.device, cmd.field, cmd.id,
                                    cmd.cmd, cmd.duration_ms, cmd.iat, cmd.exp, cmd.ctr);
      expect_eq(name + " signing_string", buf, want_ss);
    }
    bool synced = c->get("time_synced")->b;
    uint64_t now = c->get("now_ms")->n;
    cmdauth::Result r = cmdauth::verify_command(cfg, cmd, synced, now);
    expect_eq(name + " verdict", cmdauth::reason(r), cstr(c->get("expect")));
    // Accepting must be what persists: re-verifying after storing ctr is a replay.
    if (r == cmdauth::ACCEPT) {
      cfg.last_ctr = cmd.ctr;
      expect_eq(name + " replay-after-accept", cmdauth::reason(cmdauth::verify_command(cfg, cmd, synced, now)),
                "replay");
    }
  }

  int n_ack = 0;
  for (auto& a : root->get("acks")->a) {
    n_ack++;
    cmdauth::Config cfg{};
    std::snprintf(cfg.tenant, sizeof(cfg.tenant), "%s", cstr(a->get("tenant")));
    std::snprintf(cfg.device, sizeof(cfg.device), "%s", cstr(a->get("device")));
    std::snprintf(cfg.field, sizeof(cfg.field), "%s", "any-field");
    cfg.has_key = cmdauth::parse_key_hex(cstr(a->get("dk_hex")), cfg.key);
    char buf[cmdauth::kMsgMax];
    cmdauth::build_ack_string(buf, sizeof(buf), cfg.tenant, cfg.device, cstr(a->get("id")),
                              cstr(a->get("result")), a->get("ctr")->n);
    expect_eq(std::string("ack ") + cstr(a->get("result")) + " signing_string", buf,
              cstr(a->get("signing_string")));
    char hex[65];
    bool ok = cmdauth::sign_ack_hex(cfg, cstr(a->get("id")), cstr(a->get("result")), a->get("ctr")->n, hex);
    expect_eq(std::string("ack ") + cstr(a->get("result")) + " sig", ok ? hex : "<error>",
              cstr(a->get("sig")));
  }

  // Key-hex validation (SET_CMD_KEY): 64 hex only.
  uint8_t k[32];
  checks++;
  if (cmdauth::parse_key_hex("abc", k) || cmdauth::parse_key_hex(std::string(64, 'g').c_str(), k) ||
      !cmdauth::parse_key_hex(std::string(64, 'A').c_str(), k)) {
    failures++;
    std::printf("FAIL parse_key_hex validation\n");
  }

  std::printf("cmd_auth_v2 host test: %d command vectors, %d ack vectors, %d checks, %d failures\n",
              n_cmd, n_ack, checks, failures);
  return failures == 0 ? 0 : 1;
}
