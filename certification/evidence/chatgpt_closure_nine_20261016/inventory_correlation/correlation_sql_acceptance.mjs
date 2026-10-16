// PGlite executes real PostgreSQL SQL in WASM. This is NOT native PG16 or live acceptance.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const [repo, modulePath, output] = process.argv.slice(2);
const { PGlite } = await import(pathToFileURL(modulePath));
const db = new PGlite();
const evidence=path.join(repo,'certification/evidence/chatgpt_closure_nine_20261016/inventory_correlation');
const passed=[];
async function query(sql,params=[]) {return (await db.query(sql,params)).rows;}
async function check(name,fn) {await fn();passed.push(name);}
async function refuses(sql,params=[],code='23514') {await assert.rejects(()=>query(sql,params),e=>e.code===code);}
const tenant='00000000-0000-4000-8000-000000000001';
const other='00000000-0000-4000-8000-000000000002';
try {
 await db.exec(fs.readFileSync(path.join(evidence,'correlation_sql_fixture.sql'),'utf8'));
 await check('red: base lacks durable correlation columns',async()=>{
  await refuses('SELECT correlation_id FROM decision_record',[],'42703');
 });
 const migrationPaths=['migrations/v235_decision_chain_correlation.sql','services/decision-service/migrations/036_decision_chain_correlation.sql'];
 for(const p of migrationPaths) await db.exec(fs.readFileSync(path.join(repo,p),'utf8'));
 for(const p of migrationPaths) await db.exec(fs.readFileSync(path.join(repo,p),'utf8'));
 await db.exec('SET ROLE correlation_probe');
 await query("SELECT set_config('app.current_tenant',$1,false)",[tenant]);
 const root=async(id)=> (await query('INSERT INTO decision_record(decision_id,tenant_id) VALUES($1,$2) RETURNING correlation_id',[id,tenant]))[0].correlation_id;
 const corr=await root('decision-a'); const corr2=await root('decision-b');
 await check('root identities are distinct server UUIDs',async()=>{assert.match(corr,/^[0-9a-f-]{36}$/);assert.notEqual(corr,corr2);});
 await check('inbound root identity refused',()=>refuses('INSERT INTO decision_record(decision_id,tenant_id,correlation_id) VALUES($1,$2,$3)',['forged',tenant,corr]));
 await check('root replay retains stored identity',async()=>{await query("INSERT INTO decision_record(decision_id,tenant_id) VALUES('decision-a',$1) ON CONFLICT DO NOTHING",[tenant]);assert.equal((await query("SELECT correlation_id FROM decision_record WHERE decision_id='decision-a'"))[0].correlation_id,corr);});
 await query("INSERT INTO decision_reviews VALUES ('review-a',$1,'decision-a',NULL)",[tenant]);
 await query("INSERT INTO decision_execution_plans VALUES ('plan-a',$1,'decision-a','review-a',NULL)",[tenant]);
 await query("INSERT INTO decision_dispatch_authorizations VALUES ('auth-a',$1,'decision-a','review-a','plan-a',NULL)",[tenant]);
 await query("INSERT INTO decision_execution_requests VALUES ('request-a',$1,'decision-a','plan-a','auth-a','queued',NULL)",[tenant]);
 for(const t of ['decision_reviews','decision_execution_plans','decision_dispatch_authorizations','decision_execution_requests']) await check(`${t} inherits same stored identity`,async()=>assert.equal((await query(`SELECT correlation_id FROM ${t}`))[0].correlation_id,corr));
 await check('same-tenant wrong parent relation refused',()=>refuses("INSERT INTO decision_execution_plans VALUES ('bad-plan',$1,'decision-b','review-a',NULL)",[tenant],'23503'));
 await check('caller correlation mismatch refused',()=>refuses("INSERT INTO decision_reviews VALUES ('bad-review',$1,'decision-a',$2)",[tenant,corr2]));
 await check('identity immutable',()=>refuses("UPDATE decision_execution_requests SET correlation_id=$1 WHERE execution_request_id='request-a'",[corr2]));
 await check('parent key immutable',()=>refuses("UPDATE decision_execution_requests SET decision_id='decision-b' WHERE execution_request_id='request-a'"));
 await check('operational update allowed',async()=>{await query("UPDATE decision_execution_requests SET status='accepted' WHERE execution_request_id='request-a'");assert.equal((await query('SELECT correlation_id FROM decision_execution_requests'))[0].correlation_id,corr);});
 await check('legacy unknown identity retained',async()=>{await query("INSERT INTO decision_reviews VALUES ('legacy-review',$1,'legacy',NULL)",[tenant]);assert.equal((await query("SELECT correlation_id FROM decision_reviews WHERE review_id='legacy-review'"))[0].correlation_id,null);});
 await query("INSERT INTO dispatch_decisions VALUES ('disp-a',$1,NULL)",[tenant]);
 await query("INSERT INTO execution_ledger VALUES ('ledger-a',$1,'disp-a','unchanged-hash',NULL)",[tenant]);
 await check('legacy dispatch trace is distinct and ledger inherits it',async()=>{const r=(await query('SELECT correlation_id,content_hash FROM execution_ledger'))[0];assert.notEqual(r.correlation_id,corr);assert.equal(r.correlation_id,(await query('SELECT correlation_id FROM dispatch_decisions'))[0].correlation_id);assert.equal(r.content_hash,'unchanged-hash');});
 const run='10000000-0000-4000-8000-000000000001';
 await query("INSERT INTO as_applied_irrigation_runs VALUES ($1,$2,'decision-a','auth-a','plan-a',NULL)",[run,tenant]);
 await query("INSERT INTO as_applied_irrigation_receipts VALUES ('20000000-0000-4000-8000-000000000001',$1,$2,'receipt-hash',NULL)",[tenant,run]);
 await check('physical receipt follows run parent without digest rewrite',async()=>{const r=(await query('SELECT correlation_id,receipt_digest FROM as_applied_irrigation_receipts'))[0];assert.equal(r.correlation_id,corr);assert.equal(r.receipt_digest,'receipt-hash');});
 await query("SELECT set_config('app.current_tenant',$1,false)",[other]);
 await check('cross-tenant trace invisible',async()=>assert.equal((await query('SELECT * FROM decision_record')).length,0));
 await check('cross-tenant parent refused',()=>refuses("INSERT INTO decision_reviews VALUES ('cross',$1,'decision-a',NULL)",[other],'23503'));
 await query("SELECT set_config('app.current_tenant','',false)");
 await check('missing tenant context denies root write',()=>refuses("INSERT INTO decision_record(decision_id,tenant_id) VALUES('missing',$1)",[tenant],'42501'));
 await query("SELECT set_config('app.current_tenant',$1,false)",[tenant]);
 await check('rollback leaves no trace row',async()=>{await db.exec('BEGIN');await root('rollback');await db.exec('ROLLBACK');assert.equal((await query("SELECT * FROM decision_record WHERE decision_id='rollback'")).length,0);});
 fs.writeFileSync(output,JSON.stringify({engine:'PGlite WASM PostgreSQL',version:(await query('SELECT version() AS v'))[0].v,fixture:'minimal relational projection, not complete migration chain',native_postgresql:false,production_acceptance:false,passed:passed.length,cases:passed},null,2)+'\n');
 console.log(JSON.stringify({passed:passed.length,output}));
} finally {await db.close();}
