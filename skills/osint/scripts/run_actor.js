#!/usr/bin/env node
/**
 * Apify Actor Runner - Runs Apify actors and exports results.
 * Embedded from: github.com/apify/agent-skills (apify-ultimate-scraper)
 * Version: 1.3.0
 *
 * Usage:
 *   # Quick answer (display in chat, no file saved)
 *   node scripts/run_actor.js --actor ACTOR_ID --input '{}'
 *
 *   # Export to file
 *   node scripts/run_actor.js --actor ACTOR_ID --input '{}' --output leads.csv --format csv
 *
 * Env: APIFY_TOKEN or APIFY_API_TOKEN (either works)
 *
 * Investigators Copilot spend guardrails (2026-10-10; upstream apify/agent-skills dropped
 * this runner, so this is a maintained fork): every run is capped with
 * maxItems + maxTotalChargeUsd, deprecated actors are refused, and a price
 * probe warns above $5 and refuses above $20 without --confirm-spend.
 */

import { parseArgs } from 'node:util';
import { writeFileSync, readFileSync, statSync } from 'node:fs';

const USER_AGENT = 'osint-skill/3.1 (apify-agent-skills/apify-ultimate-scraper-1.3.0)';

function authHeaders(token, extra = {}) {
    return {
        ...extra,
        'Authorization': `Bearer ${token}`,
        'User-Agent': USER_AGENT,
    };
}

function parseCliArgs() {
    const options = {
        actor: { type: 'string', short: 'a' },
        input: { type: 'string', short: 'i' },
        output: { type: 'string', short: 'o' },
        format: { type: 'string', short: 'f', default: 'csv' },
        timeout: { type: 'string', short: 't', default: '600' },
        'poll-interval': { type: 'string', default: '5' },
        'max-items': { type: 'string', default: '100' },
        'max-charge-usd': { type: 'string', default: '5' },
        'confirm-spend': { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h' },
    };

    const { values } = parseArgs({ options, allowPositionals: false });

    if (values.help) {
        printHelp();
        process.exit(0);
    }

    if (!values.actor) {
        console.error('Error: --actor is required');
        printHelp();
        process.exit(1);
    }

    if (!values.input) {
        console.error('Error: --input is required');
        printHelp();
        process.exit(1);
    }

    return {
        actor: values.actor,
        input: values.input,
        output: values.output,
        format: values.format || 'csv',
        timeout: parseInt(values.timeout, 10),
        pollInterval: parseInt(values['poll-interval'], 10),
        maxItems: parseInt(values['max-items'], 10),
        maxChargeUsd: parseFloat(values['max-charge-usd']),
        confirmSpend: values['confirm-spend'],
    };
}

function printHelp() {
    console.log(`
Apify Actor Runner (embedded in OSINT skill)

Usage:
  node scripts/run_actor.js --actor ACTOR_ID --input '{}'

Options:
  --actor, -a       Actor ID (e.g., compass/crawler-google-places) [required]
  --input, -i       Actor input as JSON string [required]
  --output, -o      Output file path (optional - if not provided, displays quick answer)
  --format, -f      Output format: csv, json (default: csv)
  --timeout, -t     Max wait time in seconds (default: 600)
  --poll-interval   Seconds between status checks (default: 5)
  --max-items       Hard cap on dataset items (default: 100)
  --max-charge-usd  Hard cap on pay-per-event spend in USD (default: 5)
  --confirm-spend   Required when the estimated cost exceeds $20
  --help, -h        Show this help message

Env: APIFY_TOKEN or APIFY_API_TOKEN (either works)
`);
}

const WARN_USD = 5;
const CONFIRM_USD = 20;

// One event's price. Store prices are tiered by plan (FREE..DIAMOND); use the
// highest tier so the estimate is an upper bound, never an undercount.
function eventPriceUsd(event) {
    if (typeof event.eventPriceUsd === 'number') return event.eventPriceUsd;
    const tiers = Object.values(event.eventTieredPricingUsd || {});
    return Math.max(0, ...tiers.map((t) => t.tieredEventPriceUsd || 0));
}

// Price of one dataset item / one event from the actor's current pricing entry.
function unitPriceUsd(pricing) {
    if (!pricing) return 0;
    if (pricing.pricingModel === 'PRICE_PER_DATASET_ITEM') return pricing.pricePerUnitUsd || 0;
    if (pricing.pricingModel === 'PAY_PER_EVENT') {
        const events = (pricing.pricingPerEvent || {}).actorChargeEvents || {};
        return Math.max(0, ...Object.values(events).map(eventPriceUsd));
    }
    return 0;
}

async function probeActor(token, actorId, maxItems) {
    const url = `https://api.apify.com/v2/acts/${actorId.replace('/', '~')}`;
    // Store actors are public: probe without the token first, then retry
    // authenticated for private actors (which return 404 anonymously).
    let response = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
    if (response.status === 404 || response.status === 401) {
        response = await fetch(url, { headers: authHeaders(token) });
    }
    if (response.status === 404) {
        console.error(`Error: Actor '${actorId}' not found`);
        process.exit(1);
    }
    if (!response.ok) {
        console.error(`Warning: price probe failed (${response.status}); caps still apply`);
        return { deprecated: false, estimateUsd: 0, model: 'unknown' };
    }
    const actor = (await response.json()).data || {};
    const infos = actor.pricingInfos || [];
    const pricing = infos.length ? infos[infos.length - 1] : null;
    const unit = unitPriceUsd(pricing);
    return {
        deprecated: Boolean(actor.isDeprecated),
        model: pricing ? pricing.pricingModel : 'FREE',
        unitUsd: unit,
        estimateUsd: unit * maxItems,
    };
}

function enforceSpendPolicy(probe, args) {
    if (probe.deprecated) {
        console.error(`Error: actor '${args.actor}' is deprecated on Apify Store; pick a maintained actor`);
        process.exit(4);
    }
    const est = Math.min(probe.estimateUsd, args.maxChargeUsd || probe.estimateUsd);
    console.error(`Pricing: ${probe.model}; est. up to $${est.toFixed(2)} (cap maxItems=${args.maxItems}, maxTotalChargeUsd=$${args.maxChargeUsd})`);
    if (probe.estimateUsd > CONFIRM_USD && !args.confirmSpend) {
        console.error(`Refusing: estimate $${probe.estimateUsd.toFixed(2)} > $${CONFIRM_USD}. Re-run with --confirm-spend or lower --max-items.`);
        process.exit(5);
    }
    if (probe.estimateUsd > WARN_USD) {
        console.error(`WARNING: estimate $${probe.estimateUsd.toFixed(2)} exceeds $${WARN_USD}`);
    }
}

async function startActor(token, actorId, inputJson, caps = {}) {
    const apiActorId = actorId.replace('/', '~');
    const query = new URLSearchParams();
    if (caps.maxItems) query.set('maxItems', String(caps.maxItems));
    if (caps.maxChargeUsd) query.set('maxTotalChargeUsd', String(caps.maxChargeUsd));
    const url = `https://api.apify.com/v2/acts/${apiActorId}/runs?${query}`;

    let data;
    try {
        data = JSON.parse(inputJson);
    } catch (e) {
        console.error(`Error: Invalid JSON input: ${e.message}`);
        process.exit(1);
    }

    const response = await fetch(url, {
        method: 'POST',
        headers: authHeaders(token, {
            'Content-Type': 'application/json',
        }),
        body: JSON.stringify(data),
    });

    if (response.status === 404) {
        console.error(`Error: Actor '${actorId}' not found`);
        process.exit(1);
    }

    if (!response.ok) {
        const text = await response.text();
        console.error(`Error: API request failed (${response.status}): ${text}`);
        process.exit(1);
    }

    const result = await response.json();
    return {
        runId: result.data.id,
        datasetId: result.data.defaultDatasetId,
    };
}

async function pollUntilComplete(token, runId, timeout, interval) {
    const url = `https://api.apify.com/v2/actor-runs/${runId}`;
    const startTime = Date.now();
    let lastStatus = null;

    while (true) {
        const response = await fetch(url, { headers: authHeaders(token) });
        if (!response.ok) {
            const text = await response.text();
            console.error(`Error: Failed to get run status: ${text}`);
            process.exit(1);
        }

        const result = await response.json();
        const status = result.data.status;

        if (status !== lastStatus) {
            console.log(`Status: ${status}`);
            lastStatus = status;
        }

        if (['SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'].includes(status)) {
            return status;
        }

        const elapsed = (Date.now() - startTime) / 1000;
        if (elapsed > timeout) {
            console.error(`Warning: Timeout after ${timeout}s, actor still running`);
            return 'TIMED-OUT';
        }

        await sleep(interval * 1000);
    }
}

async function downloadResults(token, datasetId, outputPath, format) {
    const url = `https://api.apify.com/v2/datasets/${datasetId}/items?format=json`;

    const response = await fetch(url, {
        headers: authHeaders(token),
    });

    if (!response.ok) {
        const text = await response.text();
        console.error(`Error: Failed to download results: ${text}`);
        process.exit(1);
    }

    const data = await response.json();

    if (format === 'json') {
        writeFileSync(outputPath, JSON.stringify(data, null, 2));
    } else {
        if (data.length > 0) {
            const fieldnames = Object.keys(data[0]);
            const csvLines = [fieldnames.join(',')];

            for (const row of data) {
                const values = fieldnames.map((key) => {
                    let value = row[key];
                    if (typeof value === 'string' && value.length > 200) {
                        value = value.slice(0, 200) + '...';
                    } else if (Array.isArray(value) || (typeof value === 'object' && value !== null)) {
                        value = JSON.stringify(value) || '';
                    }
                    if (value === null || value === undefined) return '';
                    const strValue = String(value);
                    if (strValue.includes(',') || strValue.includes('"') || strValue.includes('\n')) {
                        return `"${strValue.replace(/"/g, '""')}"`;
                    }
                    return strValue;
                });
                csvLines.push(values.join(','));
            }
            writeFileSync(outputPath, csvLines.join('\n'));
        } else {
            writeFileSync(outputPath, '');
        }
    }

    console.log(`Saved to: ${outputPath}`);
}

async function displayQuickAnswer(token, datasetId) {
    const url = `https://api.apify.com/v2/datasets/${datasetId}/items?format=json`;

    const response = await fetch(url, {
        headers: authHeaders(token),
    });

    if (!response.ok) {
        const text = await response.text();
        console.error(`Error: Failed to download results: ${text}`);
        process.exit(1);
    }

    const data = await response.json();
    const total = data.length;

    if (total === 0) {
        console.log('\nNo results found.');
        return;
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`TOP 5 RESULTS (of ${total} total)`);
    console.log('='.repeat(60));

    for (let i = 0; i < Math.min(5, data.length); i++) {
        const item = data[i];
        console.log(`\n--- Result ${i + 1} ---`);

        for (const [key, value] of Object.entries(item)) {
            let displayValue = value;
            if (typeof value === 'string' && value.length > 100) {
                displayValue = value.slice(0, 100) + '...';
            } else if (Array.isArray(value) || (typeof value === 'object' && value !== null)) {
                const jsonStr = JSON.stringify(value);
                displayValue = jsonStr.length > 100 ? jsonStr.slice(0, 100) + '...' : jsonStr;
            }
            console.log(`  ${key}: ${displayValue}`);
        }
    }

    console.log(`\n${'='.repeat(60)}`);
    if (total > 5) {
        console.log(`Showing 5 of ${total} results.`);
    }
    console.log(`Full data: https://console.apify.com/storage/datasets/${datasetId}`);
    console.log('='.repeat(60));
}

function reportSummary(outputPath, format) {
    const stats = statSync(outputPath);
    const content = readFileSync(outputPath, 'utf-8');
    let count;
    try {
        if (format === 'json') {
            const data = JSON.parse(content);
            count = Array.isArray(data) ? data.length : 1;
        } else {
            const lines = content.split('\n').filter((line) => line.trim());
            count = Math.max(0, lines.length - 1);
        }
    } catch {
        count = 'unknown';
    }
    console.log(`Records: ${count}`);
    console.log(`Size: ${stats.size.toLocaleString()} bytes`);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
    const args = parseCliArgs();

    // Accept both APIFY_TOKEN and APIFY_API_TOKEN
    const token = process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN;
    if (!token) {
        console.error('Error: APIFY_TOKEN not found');
        console.error('Set APIFY_TOKEN or APIFY_API_TOKEN env var');
        console.error('Get your token: https://console.apify.com/account/integrations');
        process.exit(1);
    }

    const probe = await probeActor(token, args.actor, args.maxItems);
    enforceSpendPolicy(probe, args);

    console.log(`Starting actor: ${args.actor}`);
    const { runId, datasetId } = await startActor(token, args.actor, args.input,
        { maxItems: args.maxItems, maxChargeUsd: args.maxChargeUsd });
    console.log(`Run ID: ${runId}`);
    console.log(`Dataset ID: ${datasetId}`);

    const status = await pollUntilComplete(token, runId, args.timeout, args.pollInterval);

    if (status !== 'SUCCEEDED') {
        console.error(`Error: Actor run ${status}`);
        console.error(`Details: https://console.apify.com/actors/runs/${runId}`);
        process.exit(1);
    }

    if (args.output) {
        await downloadResults(token, datasetId, args.output, args.format);
        reportSummary(args.output, args.format);
    } else {
        await displayQuickAnswer(token, datasetId);
    }
}

main().catch((err) => {
    console.error(`Error: ${err.message}`);
    process.exit(1);
});
