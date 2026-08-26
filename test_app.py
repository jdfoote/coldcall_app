import pytest
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

import app as app_module
from app import Caller, write_to_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def caller_fn(tmp_path):
    return tmp_path / 'assessments.csv'


@pytest.fixture
def two_students():
    return pd.Series(['Alice', 'Bob'])


@pytest.fixture
def three_students():
    return pd.Series(['Alice', 'Bob', 'Carol'])


@pytest.fixture
def fresh_caller(caller_fn, two_students):
    return Caller(str(caller_fn), two_students)


@pytest.fixture
def three_caller(caller_fn, three_students):
    return Caller(str(caller_fn), three_students)


@pytest.fixture
def history_caller(caller_fn, two_students):
    # Alice called twice, Bob once
    caller_fn.write_text(
        'name,date,answered,assessment\n'
        'Alice,2024-01-01,T,G\n'
        'Alice,2024-01-02,T,G\n'
        'Bob,2024-01-01,T,M\n'
    )
    return Caller(str(caller_fn), two_students)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client wired to a temp course directory."""
    course = 'test_course'
    assessments = tmp_path / 'assessments'
    course_path = assessments / course
    course_path.mkdir(parents=True)

    pd.DataFrame({'Name': ['Alice', 'Bob', 'Carol']}).to_csv(
        course_path / f'{course}_students.csv', index=False
    )

    monkeypatch.setattr(app_module, 'ASSESSMENTS_DIR', assessments)
    monkeypatch.setattr(app_module, 'ALLOWED_COURSES', [course])
    app_module.callers.clear()

    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        c.course = course
        yield c

    app_module.callers.clear()


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

class TestWeights:
    def test_equal_weights_with_no_history(self, fresh_caller):
        assert fresh_caller.weights_dict['Alice'] == fresh_caller.weights_dict['Bob']

    def test_more_calls_lowers_weight(self, history_caller):
        assert history_caller.weights_dict['Alice'] < history_caller.weights_dict['Bob']

    def test_weight_formula(self, history_caller):
        # Alice called twice: (1/2)^2 = 0.25; Bob once: (1/2)^1 = 0.5
        assert history_caller.weights_dict['Alice'] == pytest.approx(0.25)
        assert history_caller.weights_dict['Bob'] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# get_random_student — basic selection
# ---------------------------------------------------------------------------

class TestGetRandomStudent:
    def test_excludes_last_chosen(self, fresh_caller):
        for _ in range(20):
            fresh_caller.last_chosen = 'Alice'
            assert fresh_caller.get_random_student() == 'Bob'

    def test_updates_last_chosen(self, fresh_caller):
        fresh_caller.last_chosen = 'Alice'
        result = fresh_caller.get_random_student()
        assert fresh_caller.last_chosen == result == 'Bob'


# ---------------------------------------------------------------------------
# Absent
# ---------------------------------------------------------------------------

class TestAbsent:
    def test_mark_absent_adds_to_set(self, fresh_caller):
        fresh_caller.mark_absent('Alice')
        assert 'Alice' in fresh_caller.absent_students

    def test_absent_student_not_selected(self, three_caller):
        three_caller.mark_absent('Alice')
        for _ in range(30):
            assert three_caller.get_random_student() != 'Alice'

    def test_absent_loaded_from_file(self, caller_fn, two_students):
        today = date.today()
        caller_fn.write_text(
            f'name,date,answered,assessment\n'
            f'Alice,{today},F,\n'
        )
        caller = Caller(str(caller_fn), two_students)
        assert 'Alice' in caller.absent_students


# ---------------------------------------------------------------------------
# Skip
# ---------------------------------------------------------------------------

class TestSkip:
    def test_mark_skipped_adds_to_set(self, fresh_caller):
        fresh_caller.mark_skipped('Alice')
        assert 'Alice' in fresh_caller.skipped_students

    def test_clear_skipped_empties_set(self, fresh_caller):
        fresh_caller.mark_skipped('Alice')
        fresh_caller.mark_skipped('Bob')
        fresh_caller.clear_skipped()
        assert fresh_caller.skipped_students == set()

    def test_skipped_student_not_selected(self, three_caller):
        three_caller.mark_skipped('Alice')
        for _ in range(30):
            assert three_caller.get_random_student() != 'Alice'

    def test_skip_resets_when_all_non_absent_exhausted(self, fresh_caller):
        # last_chosen='Bob', both skipped → curr_weights={Alice}, non_skipped={} → reset
        fresh_caller.last_chosen = 'Bob'
        fresh_caller.skipped_students = {'Alice', 'Bob'}
        result = fresh_caller.get_random_student()
        assert result == 'Alice'
        assert fresh_caller.skipped_students == set()

    def test_skipped_absent_students_dont_count_toward_exhaustion(self, three_caller):
        # Carol is absent; Alice and Bob are skipped → all non-absent exhausted → reset
        three_caller.mark_absent('Carol')
        three_caller.last_chosen = 'Bob'
        three_caller.skipped_students = {'Alice', 'Bob'}
        result = three_caller.get_random_student()
        assert result in ('Alice', 'Bob')
        assert three_caller.skipped_students == set()


# ---------------------------------------------------------------------------
# Date reset
# ---------------------------------------------------------------------------

class TestDateReset:
    def test_date_change_clears_absent(self, fresh_caller):
        fresh_caller.mark_absent('Alice')
        fresh_caller.today = date.today() - timedelta(days=1)
        fresh_caller._check_date()
        assert fresh_caller.absent_students == set()

    def test_date_change_clears_skipped(self, fresh_caller):
        fresh_caller.mark_skipped('Alice')
        fresh_caller.today = date.today() - timedelta(days=1)
        fresh_caller._check_date()
        assert fresh_caller.skipped_students == set()

    def test_no_reset_on_same_day(self, fresh_caller):
        fresh_caller.mark_skipped('Alice')
        fresh_caller._check_date()
        assert 'Alice' in fresh_caller.skipped_students


# ---------------------------------------------------------------------------
# write_to_file
# ---------------------------------------------------------------------------

class TestWriteToFile:
    def test_creates_file_with_header(self, tmp_path):
        fn = tmp_path / 'out.csv'
        write_to_file('Alice', fn, 'T', 'G')
        lines = fn.read_text().splitlines()
        assert lines[0] == 'name,date,answered,assessment'

    def test_writes_data_row(self, tmp_path):
        fn = tmp_path / 'out.csv'
        write_to_file('Alice', fn, 'T', 'G')
        lines = fn.read_text().splitlines()
        assert lines[1].startswith('Alice,')
        assert ',T,G' in lines[1]

    def test_appends_without_duplicate_header(self, tmp_path):
        fn = tmp_path / 'out.csv'
        write_to_file('Alice', fn, 'T', 'G')
        write_to_file('Bob', fn, 'T', 'M')
        lines = fn.read_text().splitlines()
        assert len(lines) == 3
        assert lines.count('name,date,answered,assessment') == 1
        assert 'Bob' in lines[2]


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_coldcaller_get_renders_page(self, client):
        r = client.get(f'/coldcaller/{client.course}')
        assert r.status_code == 200

    def test_coldcaller_post_renders_a_student(self, client):
        r = client.post(f'/coldcaller/{client.course}')
        assert r.status_code == 200
        body = r.data.decode()
        assert any(name in body for name in ('Alice', 'Bob', 'Carol'))

    def test_skip_marks_student_skipped(self, client):
        r = client.post(f'/coldcaller/{client.course}')
        student = r.data.decode()
        client.post('/response_quality', data={
            'studentName': student,
            'buttonValue': 'get_next',
            'course': client.course,
        })
        assert student in app_module.callers[client.course].skipped_students

    def test_evaluation_clears_skipped(self, client):
        # Skip first student
        r = client.post(f'/coldcaller/{client.course}')
        first = r.data.decode()
        r = client.post('/response_quality', data={
            'studentName': first,
            'buttonValue': 'get_next',
            'course': client.course,
        })
        # Evaluate second student
        second = r.data.decode()
        client.post('/response_quality', data={
            'studentName': second,
            'buttonValue': 'G',
            'course': client.course,
        })
        assert app_module.callers[client.course].skipped_students == set()

    def test_absent_marks_student_absent(self, client):
        r = client.post(f'/coldcaller/{client.course}')
        student = r.data.decode()
        client.post('/response_quality', data={
            'studentName': student,
            'buttonValue': 'absent',
            'course': client.course,
        })
        assert student in app_module.callers[client.course].absent_students

    def test_invalid_course_returns_error(self, client):
        # GET skips course validation; POST calls get_course_path which aborts,
        # but the generic except in the route re-raises it as 500.
        r = client.post('/coldcaller/not_a_real_course')
        assert r.status_code >= 400
