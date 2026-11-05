def analyze_performance(completed_tasks, assigned_tasks, completed_before_deadline, present_days, working_days, customer_rating, weights=None):
    """Calculates granular KPI percentages, assigns status flags, and returns targeted recommendations."""
    
    # Calculate percentages with division-by-zero protection
    task_completion = (completed_tasks / assigned_tasks * 100) if assigned_tasks else 0
    ontime_delivery = (completed_before_deadline / completed_tasks * 100) if completed_tasks else 0
    attendance = (present_days / working_days * 100) if working_days else 0
    customer_sat = (customer_rating / 5.0 * 100) if customer_rating else 0

    if weights is None:
        try:
            from db_utils import get_weights
            weights = get_weights()
        except Exception:
            weights = {"task": 0.35, "ontime": 0.25, "satisfaction": 0.20, "attendance": 0.20}

    task_w = float(weights.get("task", 0.35))
    ontime_w = float(weights.get("ontime", 0.25))
    att_w = float(weights.get("attendance", 0.20))
    sat_w = float(weights.get("satisfaction", 0.20))

    # Calculate overall weighted score (0-100 scale) using configured weights
    overall_score = round(
        (task_completion * task_w) + 
        (ontime_delivery * ontime_w) + 
        (attendance * att_w) + 
        (customer_sat * sat_w), 1
    )

    # Status classification helper
    def get_status(score):
        if score >= 85:
            return "Strong", "strong"
        elif score >= 70:
            return "Average", "average"
        else:
            return "Weak", "weak"

    kpis = {
        "Task Completion": {"value": f"{task_completion:.1f}%", "raw": task_completion, "status": get_status(task_completion)[0], "flag": get_status(task_completion)[1]},
        "On-Time Delivery": {"value": f"{ontime_delivery:.1f}%", "raw": ontime_delivery, "status": get_status(ontime_delivery)[0], "flag": get_status(ontime_delivery)[1]},
        "Customer Satisfaction": {"value": f"{customer_sat:.1f}%", "raw": customer_sat, "status": get_status(customer_sat)[0], "flag": get_status(customer_sat)[1]},
        "Attendance": {"value": f"{attendance:.1f}%", "raw": attendance, "status": get_status(attendance)[0], "flag": get_status(attendance)[1]}
    }

    # Action plans based on specific weak areas
    action_items = {
        "On-Time Delivery": [
            "Review workload allocation and current task capacity",
            "Identify recurring bottlenecks causing deadline delays",
            "Re-evaluate time estimations during planning phases",
            "Assign time-management & priority-setting training"
        ],
        "Task Completion": [
            "Conduct a blocker assessment with team lead",
            "Break down complex tasks into smaller daily milestones",
            "Assess skill gaps for assigned project deliverables"
        ],
        "Customer Satisfaction": [
            "Review recent customer ratings or support logs",
            "Enroll in communication & client resolution coaching",
            "Implement quality check reviews prior to delivery"
        ],
        "Attendance": [
            "Discuss potential burnout or personal constraints",
            "Explore flexible work arrangements or schedule shifts",
            "Review leave patterns and attendance policy compliance"
        ]
    }

    # Identify primary improvement area (lowest scoring KPI)
    weakest_kpi = min(kpis.keys(), key=lambda k: kpis[k]["raw"])
    
    # Summary rating
    if overall_score >= 85:
        summary_text = "— Excellent Performance"
    elif overall_score >= 70:
        summary_text = "— Satisfactory"
    else:
        summary_text = "— Needs Improvement"

    return {
        "overall_score": overall_score,
        "summary_text": summary_text,
        "kpis": kpis,
        "primary_focus": weakest_kpi if kpis[weakest_kpi]["flag"] != "strong" else "None (Maintain standard)",
        "actions": action_items.get(weakest_kpi, ["Maintain current performance standards."]) if kpis[weakest_kpi]["flag"] != "strong" else ["Sustain consistent output and mentor peers."]
    }