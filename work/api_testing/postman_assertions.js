// Shared source for generated Postman post-response scripts.
// Each request prepends its exact Test Case ID and independently declared contract.
function valueAt(object, path) {
    return String(path).split('.').reduce((current, key) => current == null ? undefined : current[key], object);
}
function equalValue(actual, expected, label) {
    if (typeof expected === 'number') {
        pm.expect(actual, label + ' exists').to.not.equal(undefined);
        pm.expect(actual, label + ' is not null').to.not.equal(null);
        pm.expect(Number(actual), label).to.equal(expected);
    } else {
        pm.expect(actual, label).to.deep.equal(expected);
    }
}
function assertFields(actual, fields, label) {
    Object.keys(fields).forEach(key => equalValue(valueAt(actual, key), fields[key], label + '.' + key));
}
// Assert the API contract independently of database cleanup.
pm.test(caseId + ' ' + stepId + ': HTTP status', () => pm.expect(pm.response.code).to.equal(expected.status));
pm.test(caseId + ' ' + stepId + ': response values and structure', () => {
    if (expected.empty_body) {
        pm.expect(pm.response.text()).to.equal('');
        return;
    }
    pm.expect(pm.response.headers.get('Content-Type')).to.include('application/json');
    const response = pm.response.json();
    const entity = response.data === undefined ? response : response.data;
    if (expected.object) assertFields(entity, expected.object, 'entity');
    if (expected.root_fields) assertFields(response, expected.root_fields, 'response');
    if (expected.rows) {
        let records = expected.row_path ? valueAt(response, expected.row_path) :
            (Array.isArray(response) ? response : (response.data === undefined ? response.results : response.data));
        pm.expect(records, 'response record array').to.be.an('array');
        pm.expect(records.length, 'exact selected record count').to.equal(expected.rows.length);
        expected.rows.forEach((fields, index) => assertFields(records[index], fields, 'records[' + index + ']'));
    }
    if (expected.error_contains) {
        // Error text is asserted as well as its HTTP code; product messages may
        // be Vietnamese even though the test documentation is written in English.
        pm.expect(JSON.stringify(response).toLowerCase()).to.include(expected.error_contains.toLowerCase());
    }
});
// Read test-only observations of the real database immediately after the API.
// This endpoint does not execute application logic or repair any persisted row.
const responseHash = require('crypto-js').SHA256(pm.response.text()).toString();
pm.sendRequest(pm.collectionVariables.get('base_url') + '/__test__/inspect/' + caseId, (error, auditResponse) => {
    pm.test(caseId + ' ' + stepId + ': CheckDB', () => {
        pm.expect(error, 'DB observation transport').to.equal(null);
        pm.expect(auditResponse.code).to.equal(200);
        const audit = auditResponse.json();
        pm.expect(audit.case_id).to.equal(caseId);
        pm.expect(audit.step).to.equal(stepId);
        pm.expect(audit.response_sha256, 'response bound to DB observation').to.equal(responseHash);
        const contract = expected.database;
        if (contract.unchanged) {
            pm.expect(audit.database_unchanged, 'all row and M2M field values unchanged').to.equal(true);
            pm.expect(audit.after_digest).to.equal(audit.before_digest);
        } else {
            audit.changed_models.forEach(label => pm.expect(contract.allowed_models, 'unexpected modified model ' + label).to.include(label));
            Object.keys(contract.tables).forEach(label => {
                const table = audit.tables[label];
                const rule = contract.tables[label];
                pm.expect(table, 'observed table ' + label).to.be.an('object');
                pm.expect(table.after.length - table.before.length, label + ' row delta').to.equal(rule.delta);
                rule.rows.forEach(selection => {
                    const record = table.after.find(entry => entry.id === selection.id);
                    pm.expect(record, label + ' persisted id ' + selection.id).to.be.an('object');
                    assertFields(record, selection.fields, label + '[' + selection.id + ']');
                    const previous = table.before.find(entry => entry.id === selection.id);
                    if (previous) {
                        const editable = Object.keys(selection.fields).concat(['updated_at', 'last_interacted']);
                        Object.keys(previous).filter(field => !editable.includes(field)).forEach(field =>
                            equalValue(record[field], previous[field], label + ' preserved field ' + field));
                    }
                });
                rule.absent.forEach(id => pm.expect(table.after.some(record => record.id === id), label + ' removed id ' + id).to.equal(false));
                const changedIds = rule.rows.map(selection => selection.id).concat(rule.absent);
                table.before.filter(record => !changedIds.includes(record.id)).forEach(record =>
                    pm.expect(table.after.find(candidate => candidate.id === record.id), label + ' unrelated row ' + record.id).to.deep.equal(record));
            });
        }
        if (expected.external) {
            const calls = audit.external_calls.filter(call => call.operation === expected.external.operation);
            pm.expect(calls.length, 'recorded external transport call').to.be.greaterThan(0);
            equalValue(valueAt(calls[calls.length - 1].arguments, expected.external.argument_path), expected.external.value, 'gateway amount');
        }
    });
});
