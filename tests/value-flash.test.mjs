import test from 'node:test';
import assert from 'node:assert/strict';
import {trackChanges} from '../dist/assets/js/ui/value-flash.mjs?v=0.25.0';
test('values seen for the first time never flash',()=>{
 const seen=new Map();
 assert.deepEqual(trackChanges(seen,[{key:'a',value:'1%'}],1000),[Infinity]);
});
test('a changed value flashes and keeps its start across re-renders',()=>{
 const seen=new Map();
 trackChanges(seen,[{key:'a',value:'1%'},{key:'b',value:'—'}],1000);
 assert.deepEqual(trackChanges(seen,[{key:'a',value:'1%'},{key:'b',value:'4.2%'}],2000),[Infinity,0]);
 assert.deepEqual(trackChanges(seen,[{key:'b',value:'4.2%'}],2500),[500]);
 assert.deepEqual(trackChanges(seen,[{key:'b',value:'3.9%'}],2600),[0]);
});
