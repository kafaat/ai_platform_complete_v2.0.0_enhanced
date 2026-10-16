const { PGlite } = await import(process.env.PGLITE_MODULE_PATH || '@electric-sql/pglite');
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const repo=process.argv[2], fixture=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const pins=Object.fromEntries(['migrations/v234_learning_agronomic_review.sql','services/sahool-platform/api/phase_runtime_store.py'].map(path=>{const bytes=fs.readFileSync(`${repo}/${path}`); return [path,createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')];}));
const db=new PGlite();const checks=[];const record=name=>checks.push(name);
const sql=path=>fs.readFileSync(path.endsWith('v234_learning_agronomic_review.sql') && process.env.U07_MIGRATION_FILE ? process.env.U07_MIGRATION_FILE : `${repo}/${path}`,'utf8');
try {
 await db.exec(sql('migrations/v119_phase10_continuous_learning.sql'));
 await db.exec(sql('migrations/v151_learning_source_lineage.sql'));
 await db.query("INSERT INTO online_learning_updates (tenant_id,update_id,model_id,feature_set_id,action) VALUES ($1,'legacy','m1','f1','defer')",[fixture[0].tenant]);
 await db.exec(sql('migrations/v234_learning_agronomic_review.sql'));
 await db.exec(sql('migrations/v234_learning_agronomic_review.sql'));
 record('actual additive migration twice');
 let row=(await db.query("SELECT review_status,agronomically_approved,agronomic_review FROM online_learning_updates WHERE update_id='legacy'")).rows[0];
 assert.deepEqual(row,{review_status:'unreviewed',agronomically_approved:false,agronomic_review:null});record('legacy defaults remain unreviewed');
 await db.exec('CREATE ROLE u07_app NOSUPERUSER NOBYPASSRLS; GRANT USAGE ON SCHEMA public TO u07_app; GRANT SELECT,INSERT,UPDATE ON online_learning_updates TO u07_app; SET ROLE u07_app;');
 for (const [i, f] of fixture.entries()) {
  try {
   // Execute the exact boundaries emitted by the real writer; none injected here.
   for (const c of f.calls) await db.query(c.sql,c.args);
   // Separate readback transaction, after the real writer has committed.
   await db.exec('BEGIN');
   await db.query("SELECT set_config('app.tenant_id',$1,true)",[f.tenant]);
   row=(await db.query("SELECT review_status,agronomically_approved,agronomic_review,traceability_status FROM online_learning_updates WHERE update_id='u1'")).rows[0];
   assert.equal(row.review_status,f.expected.review_status);assert.equal(row.agronomically_approved,f.expected.agronomically_approved);assert.deepEqual(row.agronomic_review,f.expected.review);assert.equal(row.traceability_status,'traceable');
   const tenants=(await db.query('SELECT DISTINCT tenant_id FROM online_learning_updates')).rows;
   assert(tenants.every(r=>r.tenant_id===f.tenant));
   await db.exec('COMMIT');record(`writer insert/upsert case ${i} and tenant visibility`);
  } catch(e) {await db.exec('ROLLBACK');throw e;}
 }
 await db.exec('RESET ROLE');
 assert.equal((await db.query("SELECT COUNT(*)::int AS n FROM online_learning_updates WHERE update_id='u1'")).rows[0].n,2);record('same update ID remains independent per tenant');
 const good={reviewer_id:'expert',verdict:'approved',evidence_ids:['e1']};
 const bad=[null,{}, {reviewer_id:null,verdict:'approved',evidence_ids:['e1']}, {...good,reviewer_id:12},{...good,reviewer_id:' \t '},{...good,verdict:null},{...good,verdict:'rejected'},{reviewer_id:'expert',verdict:'approved'}, {...good,evidence_ids:null},{...good,evidence_ids:[]},{...good,evidence_ids:'e1'},{...good,evidence_ids:['']},{...good,evidence_ids:[' \t ']},{...good,evidence_ids:[null]},{...good,evidence_ids:[1]},{...good,evidence_ids:['e1',{}]}];
 for(const [i,value] of bad.entries()){
  let denied=false;
  try {await db.query("UPDATE online_learning_updates SET review_status='approved',agronomically_approved=true,agronomic_review=$1::jsonb WHERE update_id='legacy'",[value===null?null:JSON.stringify(value)]);}catch(e){assert.equal(e.code,'23514');denied=true;}
  assert(denied,`malformed approval ${i} accepted`);record(`reject malformed approval ${i}`);
 }
 for(const [status,approved,review] of [['rejected',false,{}],['approved',false,good],['unreviewed',true,null],['unknown',false,null]]){
  let denied=false;try{await db.query('UPDATE online_learning_updates SET review_status=$1,agronomically_approved=$2,agronomic_review=$3::jsonb WHERE update_id=\'legacy\'',[status,approved,review===null?null:JSON.stringify(review)]);}catch(e){assert.equal(e.code,'23514');denied=true;}assert(denied);record(`reject inconsistent ${status}/${approved}`);
 }
 await db.exec('SET ROLE u07_app; BEGIN');
 await db.query("SELECT set_config('app.tenant_id',$1,true)",[fixture[0].tenant]);
 let denied=false;try{const c=fixture[4].calls.find(c=>c.sql.includes('INSERT INTO online_learning_updates'));await db.query(c.sql,c.args);}catch(e){assert.equal(e.code,'42501');denied=true;}assert(denied);await db.exec('ROLLBACK');record('RLS rejects wrong tenant write under non-bypass role');
 console.log(JSON.stringify({engine:'PGlite WASM PostgreSQL',source_git_blobs:pins,writer_transactions:'BEGIN/COMMIT emitted by real writer recorder; separate readback transaction only',version:(await db.query('select version()')).rows[0].version,scope:'SQL constraints and captured real writer statements on isolated WASM engine; not native PG/network/runtime acceptance',checks_passed:checks.length,checks},null,2));
}finally{await db.close();}
