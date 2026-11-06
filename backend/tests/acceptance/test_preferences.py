def test_simulated_users_converge():
    from app.prefs import simulate_users

    result = simulate_users(n_users=50, n_questions=5, seed=0)
    assert result["top1_match_rate"] >= 0.8
