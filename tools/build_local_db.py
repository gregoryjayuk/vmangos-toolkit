#!/usr/bin/env python3
"""
build_local_db.py — extract the tables AHBot v2 needs out of a mysqldump .sql.gz
into a local SQLite file, so the generator can run entirely offline on any machine.

    ./build_local_db.py path/to/mangos.sql.gz mangos.sqlite

Why: world-DB content is STATIC -- playing does not change
item_template or the loot tables -- so a dump is as good as a live connection for
economy work.
"""
import gzip, sqlite3, sys, re, os

WANT = {
    "item_template", "creature", "creature_loot_template", "reference_loot_template",
    "gameobject", "gameobject_template", "gameobject_loot_template",
    "item_loot_template", "fishing_loot_template", "skinning_loot_template",
    "pickpocketing_loot_template", "npc_vendor", "creature_template",
    "spell_template",
}

CREATE_RE = re.compile(r"^CREATE TABLE `([a-z_]+)`")
COL_RE    = re.compile(r"^\s*`([a-z_0-9]+)`", re.I)
INSERT_RE = re.compile(r"^INSERT INTO `([a-z_]+)` VALUES")


def split_tuples(blob):
    """Yield lists of raw field strings from a mysqldump VALUES blob.

    Hand-rolled because field values contain commas, parentheses and escaped
    quotes; a regex or naive split gets item names like "Bloodmage's ... (Test)"
    wrong, and a silently mis-parsed loot table would poison every number
    downstream.
    """
    i, n = 0, len(blob)
    while i < n:
        while i < n and blob[i] != "(":
            i += 1
        if i >= n:
            return
        i += 1
        fields, cur, in_str, esc = [], [], False, False
        while i < n:
            c = blob[i]
            if in_str:
                if esc:
                    cur.append(c); esc = False
                elif c == "\\":
                    cur.append(c); esc = True
                elif c == "'":
                    # doubled '' is a literal quote, not a terminator
                    if i + 1 < n and blob[i + 1] == "'":
                        cur.append("''"); i += 1
                    else:
                        in_str = False; cur.append(c)
                else:
                    cur.append(c)
            else:
                if c == "'":
                    in_str = True; cur.append(c)
                elif c == ",":
                    fields.append("".join(cur)); cur = []
                elif c == ")":
                    fields.append("".join(cur))
                    yield fields
                    i += 1
                    break
                else:
                    cur.append(c)
            i += 1


def coerce(raw):
    raw = raw.strip()
    if raw == "NULL":
        return None
    if raw.startswith("'"):
        s = raw[1:-1]
        return (s.replace("\\'", "'").replace("''", "'").replace('\\"', '"')
                 .replace("\\n", "\n").replace("\\r", "\r").replace("\\\\", "\\"))
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def main(dump_path, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)
    db = sqlite3.connect(out_path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")

    cols, cur_tbl, in_create = {}, None, None
    pending, total = [], {}

    with gzip.open(dump_path, "rt", errors="replace") as f:
        for line in f:
            m = CREATE_RE.match(line)
            if m:
                in_create = m.group(1) if m.group(1) in WANT else None
                if in_create:
                    cols[in_create] = []
                continue

            if in_create:
                if line.startswith(")"):
                    c = cols[in_create]
                    ddl = ", ".join(f'"{x}"' for x in c)
                    db.execute(f'CREATE TABLE "{in_create}" ({ddl})')
                    in_create = None
                else:
                    cm = COL_RE.match(line)
                    # skip KEY / PRIMARY KEY / UNIQUE lines -- they also start with a backtick
                    if cm and not line.strip().upper().startswith(("PRIMARY", "KEY", "UNIQUE", "CONSTRAINT", "FULLTEXT")):
                        cols[in_create].append(cm.group(1))
                continue

            im = INSERT_RE.match(line)
            if im:
                cur_tbl = im.group(1) if im.group(1) in WANT else None
                pending = [line[im.end():]] if cur_tbl else []
                if line.rstrip().endswith(";"):
                    if cur_tbl:
                        flush(db, cur_tbl, cols[cur_tbl], "".join(pending), total)
                    cur_tbl, pending = None, []
                continue

            if cur_tbl is not None:
                pending.append(line)
                if line.rstrip().endswith(";"):
                    flush(db, cur_tbl, cols[cur_tbl], "".join(pending), total)
                    cur_tbl, pending = None, []

    db.commit()
    index(db)
    db.commit()
    print(f"\nwrote {out_path}")
    for t in sorted(total):
        print(f"  {t:<30} {total[t]:>9,}")
    db.close()


def flush(db, table, columns, blob, total):
    rows, ncol = [], len(columns)
    for fields in split_tuples(blob):
        if len(fields) != ncol:
            continue          # schema/dump mismatch -- skip rather than corrupt
        rows.append(tuple(coerce(x) for x in fields))
    if rows:
        ph = ",".join("?" * ncol)
        db.executemany(f'INSERT INTO "{table}" VALUES ({ph})', rows)
        total[table] = total.get(table, 0) + len(rows)
        print(f"  {table:<30} +{len(rows):,}", flush=True)


def index(db):
    for tbl, col in [
        ("item_template", "entry"), ("creature", "id"), ("creature_template", "entry"),
        ("creature_loot_template", "entry"), ("creature_loot_template", "item"),
        ("reference_loot_template", "entry"), ("gameobject_loot_template", "entry"),
        ("gameobject", "id"), ("gameobject_template", "entry"), ("npc_vendor", "item"),
        ("item_loot_template", "entry"), ("fishing_loot_template", "entry"),
        ("skinning_loot_template", "entry"), ("pickpocketing_loot_template", "entry"), ("spell_template", "Id"),
    ]:
        try:
            db.execute(f'CREATE INDEX IF NOT EXISTS "ix_{tbl}_{col}" ON "{tbl}"("{col}")')
        except sqlite3.OperationalError:
            pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(os.path.expanduser(sys.argv[1]), os.path.expanduser(sys.argv[2]))
