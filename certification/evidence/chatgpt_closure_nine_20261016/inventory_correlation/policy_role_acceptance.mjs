import {pathToFileURL} from 'node:url';
const [manifestPath,modulePath,output]=process.argv.slice(2);
const {PGlite}=await import(pathToFileURL(modulePath));
import fs from 'node:fs'; import assert from 'node:assert/strict';
const manifest=JSON.parse(fs.readFileSync(manifestPath));
const db=new PGlite(); const rows=[];
try {
 await db.exec("CREATE ROLE inventory_probe NOSUPERUSER NOBYPASSRLS; CREATE ROLE unrelated_role; CREATE ROLE inherited_group; GRANT inherited_group TO inventory_probe; CREATE TABLE raster_assets(tenant_id uuid); ALTER TABLE raster_assets ENABLE ROW LEVEL SECURITY; ALTER TABLE raster_assets FORCE ROW LEVEL SECURITY; GRANT SELECT ON raster_assets TO inventory_probe;");
 for(const [kind,target,expected] of [['public','PUBLIC',true],['self','inventory_probe',true],['inherited','inherited_group',true],['other','unrelated_role',false]]) {
  await db.exec(`CREATE POLICY scope ON raster_assets TO ${target} USING(tenant_id::text=current_setting('app.current_tenant',true)); SET ROLE inventory_probe;`);
  const result=(await db.query(manifest.policy_query,[['raster_assets']])).rows[0].jsonb_agg;
  assert.equal(result[0].applicable,expected);assert.equal(result[0].permissive,true);rows.push({kind,...result[0]});
  await db.exec('RESET ROLE; DROP POLICY scope ON raster_assets;');
 }
 await db.exec("CREATE POLICY scope ON raster_assets AS RESTRICTIVE USING(tenant_id::text=current_setting('app.current_tenant',true)); SET ROLE inventory_probe;");
 const restrictive=(await db.query(manifest.policy_query,[['raster_assets']])).rows[0].jsonb_agg[0];assert.equal(restrictive.permissive,false);assert.equal(restrictive.applicable,true);rows.push({kind:'restrictive',...restrictive});
 await db.exec('RESET ROLE; DROP POLICY scope ON raster_assets; SET ROLE inventory_probe;');
 const missing=(await db.query(manifest.policy_query,[['raster_assets']])).rows[0].jsonb_agg[0];assert.equal(missing.permissive,false);assert.equal(missing.applicable,false);rows.push({kind:'missing',...missing});
 fs.writeFileSync(output,JSON.stringify({engine:'PGlite PostgreSQL WASM',native:false,passed:rows.length,cases:rows},null,2)+'\n');console.log({passed:rows.length});
}finally{await db.close();}
