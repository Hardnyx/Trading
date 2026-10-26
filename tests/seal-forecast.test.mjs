import test from "node:test";
import assert from "node:assert/strict";
import {
  nextSessionStart,prospectiveEligibility,maturityCheck
} from "../scripts/seal_forecast.mjs";

test("only genuinely prospective issue windows may enter a permanent forecast journal",()=>{
  assert.equal(nextSessionStart("2026-10-23"),"2026-10-26");
  const snapshot={
    price_as_of:"2026-10-23",
    generated_at:"2026-10-25T18:00:00Z",
  };
  const valid=prospectiveEligibility(snapshot,"2026-10-25T20:00:00Z");
  assert.equal(valid.eligible,true);
  assert.equal(prospectiveEligibility(snapshot,"2026-10-23T18:00:00Z").eligible,false);
  assert.equal(prospectiveEligibility(snapshot,"2026-10-26T15:00:00Z").eligible,false);
  assert.equal(prospectiveEligibility({...snapshot,generated_at:"2026-10-26T01:00:00Z"},
    "2026-10-25T20:00:00Z").eligible,false);
});

test("maturity cannot be declared from an unmatured 12-month prediction",()=>{
  const origin={
    maturity_date:"2027-10-23",
    original_price_as_of:"2026-10-23",
    positions:[{symbol:"CASH",weight:1}],
    forecast:{probability_loss:.2,p05:-.1,p95:.1},
  };
  assert.equal(maturityCheck(origin,{price_as_of:"2026-10-26",assets:[]}).status,
    "immature");
  assert.equal(maturityCheck(origin,{price_as_of:"2027-10-24",assets:[]}).status,
    "mature_without_risky_positions");
});
