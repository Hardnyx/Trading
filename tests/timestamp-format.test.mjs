import test from 'node:test';
import assert from 'node:assert/strict';
import {timestampLabel,dateLabel,localTimeZone} from '../dist/assets/js/ui/format.mjs?v=0.22.0';
test('capture conversion uses the browser zone and preserves the instant across calendar days',()=>{
 const stamp='2026-10-27T02:15:11.078239+00:00';
 assert.equal(timestampLabel(stamp,'America/Lima'),'26 OCT 2026 21:15:11 · America/Lima (UTC−5)');
 assert.equal(timestampLabel(stamp,'Asia/Tokyo'),'27 OCT 2026 11:15:11 · Asia/Tokyo (UTC+9)');
 assert.equal(timestampLabel(stamp),timestampLabel(stamp,Intl.DateTimeFormat().resolvedOptions().timeZone));
 assert.equal(localTimeZone(),Intl.DateTimeFormat().resolvedOptions().timeZone);
 assert.equal(timestampLabel('2026-10-27T02:15:11Z'),timestampLabel('2026-10-26T21:15:11-05:00'));
 assert.equal(dateLabel('2026-10-26'),'26 OCT 2026');
});
test('offset is determined at the capture instant, including daylight saving changes',()=>{
 assert.match(timestampLabel('2026-07-01T02:00:00Z','America/New_York'),/30 JUN 2026 22:00:00.*UTC−4/);
 assert.match(timestampLabel('2026-12-01T02:00:00Z','America/New_York'),/30 NOV 2026 21:00:00.*UTC−5/);
 assert.equal(timestampLabel('2026-10-27T02:00:00Z','invalid/zone'),'27 OCT 2026 02:00:00 · UTC');
});
test('capture formatting rejects unknown timezone in the source and invalid instants',()=>{
 for(const value of [null,'2026-10-27','2026-10-27T02:15:11','not a date','2026-99-99T02:00:00Z'])assert.equal(timestampLabel(value),'—');
});
