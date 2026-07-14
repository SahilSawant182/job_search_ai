document.addEventListener("DOMContentLoaded", function () {
	const form            = document.getElementById("profile-form");
	const submitBtn       = document.getElementById("submit-btn");
	const welcomeCard     = document.getElementById("welcome-card");
	const loadingCard     = document.getElementById("loading-card");
	const resultsContainer= document.getElementById("results-container");
	const errorContainer  = document.getElementById("error-container");
	const errorMessage    = document.getElementById("error-message");

	const STEPS = [
		{ id: "step-profile", delay: 0 },
		{ id: "step-queries", delay: 1500 },
		{ id: "step-trends",  delay: 3500 },
		{ id: "step-filter",  delay: 8000 },
		{ id: "step-llm",     delay: 12000 },
		{ id: "step-done",    delay: 18000 },
	];

	let timers = [];

	form.addEventListener("submit", e => { e.preventDefault(); runAnalysis(); });

	function getCookie(name) {
		const r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
		return r ? r[1] : undefined;
	}

	function resetSteps() {
		STEPS.forEach(s => {
			document.getElementById(s.id).className = "pipeline-step";
		});
	}

	function markStepActive(id) {
		document.getElementById(id).classList.add("active");
	}

	function markStepDone(id) {
		const el = document.getElementById(id);
		el.className = "pipeline-step completed";
	}

	function startPipelineAnimation() {
		resetSteps();
		STEPS.forEach((step, i) => {
			const t = setTimeout(() => {
				// Complete previous
				if (i > 0) markStepDone(STEPS[i - 1].id);
				markStepActive(step.id);
			}, step.delay);
			timers.push(t);
		});
	}

	function completePipeline() {
		timers.forEach(clearTimeout);
		timers = [];
		STEPS.forEach(s => markStepDone(s.id));
	}

	function runAnalysis() {
		// Reset UI
		errorContainer.classList.add("d-none");
		welcomeCard.classList.add("d-none");
		resultsContainer.classList.add("d-none");
		loadingCard.classList.remove("d-none");

		submitBtn.disabled = true;
		submitBtn.innerHTML = '<span class="me-2" style="display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,0.4);border-top-color:#fff;border-radius:50%;animation:spin 0.8s linear infinite"></span>Analysing...';

		startPipelineAnimation();

		const params = new URLSearchParams({
			degree:    document.getElementById("degree").value,
			branch:    document.getElementById("branch").value,
			year:      document.getElementById("year").value,
			country:   document.getElementById("country").value,
			interests: document.getElementById("interests").value,
			skills:    document.getElementById("skills").value,
		});

		fetch("/api/method/job_search_ai.api.career_trends.get_career_trends", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded",
				"X-Frappe-CSRF-Token": getCookie("sid") || window.csrf_token || "",
			},
			body: params,
		})
		.then(r => {
			if (!r.ok) {
				return r.json().then(err => {
					let msg = "Server Error";
					try { msg = JSON.parse(err._server_messages)[0].message || msg; } catch(e) {}
					throw new Error(msg);
				}).catch(() => { throw new Error("HTTP " + r.status); });
			}
			return r.json();
		})
		.then(data => {
			completePipeline();
			setTimeout(() => {
				loadingCard.classList.add("d-none");
				renderResults(data.message);
				resultsContainer.classList.remove("d-none");
				resetBtn();
			}, 600);
		})
		.catch(err => {
			timers.forEach(clearTimeout);
			loadingCard.classList.add("d-none");
			welcomeCard.classList.remove("d-none");

			let msg = String(err.message || "An unexpected error occurred.");
			errorMessage.innerText = msg;
			errorContainer.classList.remove("d-none");
			resetBtn();
		});
	}

	function resetBtn() {
		submitBtn.disabled = false;
		submitBtn.innerHTML = '<i class="bi bi-stars me-2"></i>Analyze Career Trends';
	}

	/* ── Helpers ── */
	function hostname(url) {
		try { return new URL(url).hostname.replace("www.", ""); }
		catch(e) { return url.length > 40 ? url.slice(0, 40) + "…" : url; }
	}

	function isUrl(s) {
		try { new URL(s); return true; } catch(e) { return false; }
	}

	function demandClass(d) {
		const v = String(d).toLowerCase();
		if (v.includes("very high")) return "badge-demand-vhigh";
		if (v.includes("high"))      return "badge-demand-high";
		if (v.includes("moderate"))  return "badge-demand-mod";
		return "badge-demand-low";
	}

	function stageClass(s) {
		const v = String(s).toLowerCase();
		if (v.includes("emerging"))   return "badge-emerging";
		if (v.includes("growing"))    return "badge-growing";
		if (v.includes("established"))return "badge-established";
		return "badge-established";
	}

	/* ── Render ── */
	function renderResults(res) {
		const meta = res.metadata || {};

		// Timestamp
		document.getElementById("generated-time").innerText =
			new Date(res.generated_at).toLocaleString();

		// Model chip
		document.getElementById("model-badge").innerText =
			"\u{1F916} " + (meta.model || "qwen2.5:1.5b");

		// Knowledge badge
		const kbBadge = document.getElementById("knowledge-badge");
		if (meta.knowledge_hit) {
			kbBadge.innerText = "🧠 Knowledge Hit";
			kbBadge.style.background = "#ecfdf5";
			kbBadge.style.color = "#059669";
			kbBadge.style.border = "1px solid #a7f3d0";
		} else {
			kbBadge.innerText = "🌐 Live Web Search";
			kbBadge.style.background = "#fef3c7";
			kbBadge.style.color = "#d97706";
			kbBadge.style.border = "1px solid #fde68a";
		}

		// Strategy
		document.getElementById("strategy-text").innerText = res.strategy || "";

		// Metrics
		document.getElementById("metric-total").innerText =
			(meta.total_execution_time_seconds || 0).toFixed(1) + "s";
		document.getElementById("metric-search").innerText =
			(meta.search_execution_time_seconds || 0).toFixed(2) + "s";
		document.getElementById("metric-llm").innerText =
			(meta.llm_execution_time_seconds || 0).toFixed(1) + "s";
		document.getElementById("metric-prompt").innerText =
			(meta.prompt_length_characters || 0).toLocaleString();
		document.getElementById("metric-results").innerText =
			meta.search_results_used || "—";

		// Career cards
		const container = document.getElementById("career-paths");
		container.innerHTML = "";

		(res.recommended_paths || []).forEach(path => {
			const sourcesHtml = (path.sources || []).map(src => {
				if (isUrl(src)) {
					return `<a href="${src}" target="_blank" rel="noopener" class="source-link">
						<i class="bi bi-box-arrow-up-right" style="font-size:0.65rem"></i>
						${hostname(src)}
					</a>`;
				} else {
					return `<span class="source-link">${src}</span>`;
				}
			}).join("");

			const skillsHtml = (path.skills || []).map(
				s => `<span class="skill-tag">${s}</span>`
			).join("");

			const card = document.createElement("div");
			card.className = "career-card";
			card.innerHTML = `
				<div class="cc-header">
					<div>
						<div class="cc-title">${path.career}</div>
						<div class="cc-meta">
							<strong>${path.industry}</strong>
							<span class="mx-1">·</span>${path.category}
						</div>
					</div>
					<div class="cc-badges">
						<span class="badge-stage ${stageClass(path.career_stage)}">${path.career_stage}</span>
						<span class="badge-stage ${demandClass(path.future_demand)}">${path.future_demand}</span>
					</div>
				</div>

				<div class="cc-confidence-row">
					<div class="cc-confidence-label">
						<span>AI Match Confidence</span>
						<span>${path.confidence}%</span>
					</div>
					<div class="cc-progress">
						<div class="cc-progress-bar" style="width:${path.confidence}%"></div>
					</div>
				</div>

				<div class="cc-section-label">Why This Fits You</div>
				<div class="cc-why">${path.why_for_you}</div>

				${skillsHtml ? `
					<div class="cc-section-label">Required Skills</div>
					<div class="cc-skills">${skillsHtml}</div>
				` : ""}

				${sourcesHtml ? `
					<div class="cc-sources">
						<span class="cc-section-label mb-0 me-2 align-self-center">Sources:</span>
						${sourcesHtml}
					</div>
				` : ""}
			`;
			container.appendChild(card);
		});
	}
});
