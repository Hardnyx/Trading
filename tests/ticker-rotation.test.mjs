import test from 'node:test';
import assert from 'node:assert/strict';
import {tickerLayout} from '../dist/assets/js/ui/ticker-rotation.mjs?v=0.32.0';
test('the market strip stays on one row while every reference fits',()=>{
 assert.deepEqual(tickerLayout(6,1460,156),{perRow:6,rows:1});
 assert.deepEqual(tickerLayout(6,936,156),{perRow:6,rows:1});
});
test('overflowing references rotate in balanced rows',()=>{
 assert.deepEqual(tickerLayout(6,390,150),{perRow:2,rows:3});
 assert.deepEqual(tickerLayout(6,760,156),{perRow:3,rows:2});
 assert.deepEqual(tickerLayout(7,760,156),{perRow:4,rows:2});
 assert.deepEqual(tickerLayout(6,100,156),{perRow:1,rows:6});
});
test('an empty or unmeasured strip never rotates',()=>{
 assert.deepEqual(tickerLayout(0,1460,156),{perRow:0,rows:0});
 assert.deepEqual(tickerLayout(6,0,156),{perRow:6,rows:1});
});
