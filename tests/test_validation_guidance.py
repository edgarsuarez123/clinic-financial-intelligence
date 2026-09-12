from app.validation import simulation_issues


def test_guidance_preserves_known_fields_not_user_values():
    items=simulation_issues([{'loc':('body','plan','staff',0,'annual_salary'),'type':'value_error','input':'patient name', 'msg':'private value'},
        {'loc':('body','plan','staff',0,'monthly_salary','Jane Doe'),'type':'int_parsing','input':'secret'}])
    assert items[0]['field']=='plan.staff.0.annual_salary'
    assert items[1]['field']=='plan.staff.0.monthly_salary.field'
    assert not any(s in str(items) for s in ['patient name','Jane Doe','secret','private value'])


def test_guidance_is_bounded_and_actionable():
    assert simulation_issues([{'loc':('body','plan','existing_revenue_basis'),'type':'missing'}])[0]['message']=='This field is required.'
    assert len(simulation_issues([{'loc':('body','plan'),'type':'missing'}]*20))==8


def test_budget_validation_response_guides_without_echoing_input():
    from fastapi.testclient import TestClient
    from test_api import MemoryStore, login
    from test_budgets import MemoryBudgets, make_app, create_body
    store = MemoryStore()
    body = create_body()
    body['plan']['staff'][0]['annual_salary'] = 'private rejected value'
    with TestClient(make_app(store, MemoryBudgets(store))) as client:
        _, headers = login(client)
        response = client.post('/api/v1/simulations/budgets', headers=headers, json=body)
    assert response.status_code == 422
    assert response.json()['error']['issues'][0]['field'] == 'plan.staff.0.annual_salary'
    assert 'private rejected value' not in response.text
