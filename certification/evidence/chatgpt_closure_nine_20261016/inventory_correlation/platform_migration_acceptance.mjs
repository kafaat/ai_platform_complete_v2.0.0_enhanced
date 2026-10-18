// Executes exact target-table migrations, not a full platform/PostGIS installation.
import fs from 'node:fs'; import path from 'node:path'; import assert from 'node:assert/strict'; import {pathToFileURL} from 'node:url';
const [repo,modulePath,output]=process.argv.slice(2);const {PGlite}=await import(pathToFileURL(modulePath));const db=new PGlite();
const tenant='00000000-0000-4000-8000-000000000001', other='00000000-0000-4000-8000-000000000002';
const migrations=['migrations/v66_dispatch_decisions.sql','migrations/v67_dispatch_hardening.sql','migrations/v68_execution_ledger.sql','migrations/v78_decision_record.sql','migrations/v178_canonical_as_applied_irrigation_truth.sql'];
const passed=[]; const q=async(sql,args=[])=>(await db.query(sql,args)).rows;
async function check(name,fn){await fn();passed.push(name);}
async function ledger(id,decision,corr=null){return (await q("INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,outcome,content_hash,correlation_id) VALUES($1,$2,$3,'inspection','executed','unchanged',$4) RETURNING correlation_id",[id,tenant,decision,corr]))[0];}
async function run(id,decision,corr=null){return (await q(`INSERT INTO as_applied_irrigation_runs(id,tenant_id,field_id,season_id,machine_id,controller_id,decision_id,authorization_id,execution_plan_id,plan_digest,planned_depth_mm,planned_volume_m3,planned_area_ha,irrigation_capability_digest,commissioning_certification_digest,decision_content_digest,correlation_id) VALUES($1,$2,'ci-field','ci-season',$1,$1,$3,'ci-auth',$1::uuid::text,'digest',1,1,1,'digest','digest','digest',$4) RETURNING correlation_id`,[id,tenant,decision,corr]))[0];}
try{
 for(const p of migrations)await db.exec(fs.readFileSync(path.join(repo,p),'utf8'));
 await q("INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,outcome,content_hash) VALUES('legacy-orphan',$1,'missing','inspection','executed','unchanged')",[tenant]);
 await db.exec(fs.readFileSync(path.join(repo,'migrations/v235_decision_chain_correlation.sql'),'utf8'));
 await db.exec(fs.readFileSync(path.join(repo,'migrations/v235_decision_chain_correlation.sql'),'utf8'));
 // v66/v68's helper is not defined in this selected-migration fixture. Install
 // canonical read/write RLS explicitly, then execute as a non-bypass role.
 await db.exec(`CREATE ROLE platform_probe NOSUPERUSER NOBYPASSRLS; GRANT USAGE ON SCHEMA public TO platform_probe; GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO platform_probe;`);
 for(const t of ['execution_ledger','dispatch_decisions'])await db.exec(`ALTER TABLE ${t} ENABLE ROW LEVEL SECURITY; ALTER TABLE ${t} FORCE ROW LEVEL SECURITY; CREATE POLICY probe_tenant ON ${t} USING(tenant_id::text=NULLIF(current_setting('app.current_tenant',true),'')) WITH CHECK(tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));`);
 await q("INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value) VALUES('foreign-decision',$1,'inspection','{}')",[other]);
 await q("INSERT INTO dispatch_decisions(decision_id,tenant_id,recommendation_id,action_type,state,risk_level) VALUES('foreign-dispatch',$1,'ci-rec','inspection','ready','low')",[other]);
 await db.exec('SET ROLE platform_probe');await q("SELECT set_config('app.current_tenant',$1,false)",[tenant]);
 await check('historical orphan remains null',async()=>assert.equal((await q("SELECT correlation_id FROM execution_ledger WHERE ledger_id='legacy-orphan'"))[0].correlation_id,null));
 await check('new direct orphan ledger stays compatible and explicitly unbound',async()=>assert.equal((await ledger('new-orphan','missing')).correlation_id,null));
 await check('missing physical decision stays compatible and unbound',async()=>assert.equal((await run('10000000-0000-4000-8000-000000000001','missing')).correlation_id,null));
 await check('invisible foreign dispatch does not leak or inherit',async()=>assert.equal((await ledger('foreign-reference','foreign-dispatch')).correlation_id,null));
 await check('invisible foreign agronomic decision does not leak or inherit',async()=>assert.equal((await run('10000000-0000-4000-8000-000000000002','foreign-decision')).correlation_id,null));
 await check('caller cannot forge orphan correlation',()=>assert.rejects(()=>ledger('forged','missing','20000000-0000-4000-8000-000000000001'),e=>e.code==='23514'));
 await q("INSERT INTO dispatch_decisions(decision_id,tenant_id,recommendation_id,action_type,state,risk_level) VALUES('own-dispatch',$1,'ci-rec','inspection','ready','low')",[tenant]);
 const corr=(await q("SELECT correlation_id FROM dispatch_decisions WHERE decision_id='own-dispatch'"))[0].correlation_id;
 await check('actual dispatch-parent writer inherits stored identity',async()=>assert.equal((await ledger('bound','own-dispatch')).correlation_id,corr));
 await check('old outcome check still rejects queued',()=>assert.rejects(()=>q("INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,outcome,content_hash) VALUES('bad-outcome',$1,'missing','inspection','queued','unchanged')",[tenant]),e=>e.code==='23514'));
 fs.writeFileSync(output,JSON.stringify({engine:'PostgreSQL WASM',native:false,full_platform_schema:false,migration_sources:migrations,applied:'migrations/v235_decision_chain_correlation.sql',passed:passed.length,cases:passed,rls_note:'v66/v68 RLS helper absent from subset; explicit canonical fixture policy, other migrations exact'},null,2)+'\n');console.log(JSON.stringify({passed:passed.length}));
}finally{await db.close();}
