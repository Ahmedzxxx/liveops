from datetime import date, timedelta
from scheduler_engine import generate_week_schedule, get_sunday_of_week

def run_6_week_audit():
    start_sun = date(2026, 10, 11)
    agent_weekly_offs = {}

    for w in range(6):
        cur_sun = start_sun + timedelta(weeks=w)
        sched = generate_week_schedule(cur_sun.isoformat(), force_regenerate=True)
        
        # Verify daily coverage
        daily_work = {d: 0 for d in range(7)}
        daily_off = {d: 0 for d in range(7)}
        
        for slot in sched:
            agent_id = slot["agent_id"]
            d = slot["day_of_week"]
            st = slot["shift_type"]
            
            if agent_id not in agent_weekly_offs:
                agent_weekly_offs[agent_id] = []
            
            if st == "work":
                daily_work[d] += 1
            else:
                daily_off[d] += 1
                if d != 5:  # Friday is always off, record the other off day
                    agent_weekly_offs[agent_id].append((w, d))
        
        # Assert daily coverage
        for d in range(7):
            if d == 5:
                assert daily_work[d] == 0 and daily_off[d] == 6, f"Week {w} Friday failed!"
            else:
                assert daily_work[d] == 5 and daily_off[d] == 1, f"Week {w} Day {d} failed! Work={daily_work[d]}, Off={daily_off[d]}"

    # Verify each agent's off pattern across the 6 weeks
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for agent_id, offs in agent_weekly_offs.items():
        off_days = [d for w, d in offs]
        assert len(off_days) == 6, f"Agent {agent_id} did not get 6 weeks of offs!"
        # Check all 6 distinct days: 0, 1, 2, 3, 4, 6
        assert set(off_days) == {0, 1, 2, 3, 4, 6}, f"Agent {agent_id} off days mismatch: {off_days}"
        
        # Check no consecutive Thu (4) or Sat (6)
        for i in range(len(off_days) - 1):
            cur = off_days[i]
            nxt = off_days[i+1]
            assert not (cur == 4 and nxt == 4), f"Agent {agent_id} had Thu two weeks in a row!"
            assert not (cur == 6 and nxt == 6), f"Agent {agent_id} had Sat two weeks in a row!"
            assert not (cur == 4 and nxt == 6), f"Agent {agent_id} had Thu then Sat in consecutive weeks!"
            assert not (cur == 6 and nxt == 4), f"Agent {agent_id} had Sat then Thu in consecutive weeks!"
            assert not (cur == 6 and nxt == 0), f"Agent {agent_id} had Sat then Sun in consecutive weeks!"
        
        # Also check wrap-around from week 5 to week 0
        cur = off_days[5]
        nxt = off_days[0]
        assert not (cur == 6 and nxt == 0), f"Agent {agent_id} had Sat (W5) then Sun (W0) on cycle wrap!"

    print("PASS: All mathematical constraints and coverage invariants strictly satisfied across 6 weeks!")

if __name__ == "__main__":
    run_6_week_audit()
