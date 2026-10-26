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

test("weekend maturity uses the next observed common session, not a synthetic close",()=>{
  const origin={
    maturity_date:"2027-10-23",
    original_price_as_of:"2026-10-23",
    positions:[{symbol:"AAA",weight:1}],
    forecast:{probability_loss:.3,p05:-.15,p95:.35},
  };
  const market={
    price_as_of:"2027-10-25",
    assets:[{symbol:"AAA",history:[
      {date:"2026-10-23",close:100,adj_close:100},
      {date:"2027-10-22",close:110,adj_close:110},
      {date:"2027-10-25",close:120,adj_close:120},
    ]}],
  };
  const result=maturityCheck(origin,market);
  assert.equal(result.status,"eligible_outcome_approximation");
  assert.equal(result.actual_maturity_session,"2027-10-25");
  assert.ok(Math.abs(result.realized_buy_and_hold_gross-.2)<1e-12);
  market.price_as_of="2027-10-23";
  assert.equal(maturityCheck(origin,market).status,"awaiting_trading_session");
});
