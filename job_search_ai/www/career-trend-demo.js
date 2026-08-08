document.addEventListener("DOMContentLoaded", function () {
	const form = document.getElementById("profile-form");
	const submitBtn = document.getElementById("submit-btn");
	const welcomeCard = document.getElementById("welcome-card");
	const loadingCard = document.getElementById("loading-card");
	const resultsContainer = document.getElementById("results-container");
	const errorContainer = document.getElementById("error-container");
	const errorMessage = document.getElementById("error-message");

	const loadedSkillsCache = {};

	const STEPS = [
		{ id: "step-profile", delay: 0 },
		{ id: "step-queries", delay: 1500 },
		{ id: "step-trends", delay: 3500 },
		{ id: "step-filter", delay: 8000 },
		{ id: "step-llm", delay: 12000 },
		{ id: "step-done", delay: 18000 },
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
			degree: document.getElementById("degree").value,
			branch: document.getElementById("branch").value,
			year: document.getElementById("year").value,
			country: document.getElementById("country").value,
			interests: document.getElementById("interests").value,
			skills: document.getElementById("skills").value,
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
						try { msg = JSON.parse(err._server_messages)[0].message || msg; } catch (e) { }
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
		catch (e) { return url.length > 40 ? url.slice(0, 40) + "…" : url; }
	}

	function isUrl(s) {
		try { new URL(s); return true; } catch (e) { return false; }
	}

	function demandClass(d) {
		const v = String(d).toLowerCase();
		if (v.includes("very high")) return "badge-demand-vhigh";
		if (v.includes("high")) return "badge-demand-high";
		if (v.includes("moderate")) return "badge-demand-mod";
		return "badge-demand-low";
	}

	function stageClass(s) {
		const v = String(s).toLowerCase();
		if (v.includes("emerging")) return "badge-emerging";
		if (v.includes("growing")) return "badge-growing";
		if (v.includes("established")) return "badge-established";
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

				<div class="cc-skills-details d-none"></div>
				<div class="cc-action">
					<i class="bi bi-chevron-down"></i>
					<span class="action-text">Analyze Skill Gap &amp; Readiness</span>
				</div>
			`;

			card.addEventListener("click", e => {
				if (e.target.closest("a") || e.target.closest("button")) return;
				toggleCardSkills(card, path.career);
			});

			container.appendChild(card);
		});
	}

	function toggleCardSkills(card, careerName) {
		const detailsContainer = card.querySelector(".cc-skills-details");
		const actionEl = card.querySelector(".cc-action");
		if (!detailsContainer || !actionEl) return;

		const isActive = card.classList.contains("active");

		if (isActive) {
			card.classList.remove("active");
			detailsContainer.classList.add("d-none");
			actionEl.innerHTML = `<i class="bi bi-chevron-down"></i><span class="action-text">Analyze Skill Gap &amp; Readiness</span>`;
		} else {
			// Collapse all other cards first
			document.querySelectorAll(".career-card.active").forEach(otherCard => {
				if (otherCard !== card) {
					otherCard.classList.remove("active");
					const otherDetails = otherCard.querySelector(".cc-skills-details");
					if (otherDetails) otherDetails.classList.add("d-none");
					const otherAction = otherCard.querySelector(".cc-action");
					if (otherAction) {
						otherAction.innerHTML = `<i class="bi bi-chevron-down"></i><span class="action-text">Analyze Skill Gap &amp; Readiness</span>`;
					}
				}
			});

			card.classList.add("active");
			detailsContainer.classList.remove("d-none");
			actionEl.innerHTML = `<i class="bi bi-chevron-up"></i><span class="action-text">Hide analysis</span>`;

			const studentSkills = document.getElementById("skills").value;
			const cacheKey = `${careerName}_${studentSkills}`;

			if (loadedSkillsCache[cacheKey]) {
				renderSkillGapInContainer(detailsContainer, loadedSkillsCache[cacheKey], careerName);
			} else {
				fetchSkillGap(careerName, detailsContainer, studentSkills, cacheKey);
			}
		}
	}

	function fetchSkillGap(careerName, detailsContainer, studentSkills, cacheKey) {
		const params = new URLSearchParams({
			career: careerName,
			student_skills: studentSkills,
			student: "demo_student@example.com"
		});

		detailsContainer.innerHTML = `
			<div class="skills-loading">
				<div class="spinner-border text-primary spinner-border-sm" role="status"></div>
				<div class="small text-muted fw-semibold">Consulting Skill Gap Agent...</div>
			</div>
		`;

		fetch("/api/method/job_search_ai.services.skill_gap.api.analyze", {
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
						try { msg = JSON.parse(err._server_messages)[0].message || msg; } catch (e) { }
						throw new Error(msg);
					}).catch(() => { throw new Error("HTTP " + r.status); });
				}
				return r.json();
			})
			.then(data => {
				const res = data.message;
				loadedSkillsCache[cacheKey] = res;
				renderSkillGapInContainer(detailsContainer, res, careerName);
			})
			.catch(err => {
				console.error("Failed to fetch skill gap:", err);
				detailsContainer.innerHTML = `
					<div class="skills-error">
						<i class="bi bi-exclamation-circle-fill me-2"></i>Failed to retrieve skill gap analysis.
						<div class="small mt-1">${err.message || "Please try again later."}</div>
						<button class="skills-retry-btn" type="button">Retry</button>
					</div>
				`;
				const retryBtn = detailsContainer.querySelector(".skills-retry-btn");
				if (retryBtn) {
					retryBtn.addEventListener("click", e => {
						e.stopPropagation();
						fetchSkillGap(careerName, detailsContainer, studentSkills, cacheKey);
					});
				}
			});
	}

	function renderSkillGapInContainer(detailsContainer, res, careerName) {
		const matchedTags = (res.matched_skills || []).map(s => `<span class="skill-badge matched-skill"><i class="bi bi-check-circle-fill me-1 text-success"></i>${s}</span>`).join("");
		
		const missingFoundationTags = (res.missing_foundation || []).map(s => `<span class="skill-badge missing-skill"><i class="bi bi-plus-circle me-1 text-muted"></i>${s}</span>`).join("");
		const missingCoreDomainTags = (res.missing_core_domain || []).map(s => `<span class="skill-badge missing-skill"><i class="bi bi-plus-circle me-1 text-muted"></i>${s}</span>`).join("");
		const missingIndustryTags = (res.missing_industry || []).map(s => `<span class="skill-badge missing-skill"><i class="bi bi-plus-circle me-1 text-muted"></i>${s}</span>`).join("");
		const missingEmergingTags = (res.missing_emerging || []).map(s => `<span class="skill-badge missing-skill"><i class="bi bi-plus-circle me-1 text-muted"></i>${s}</span>`).join("");

		const score = res.readiness_score || 0;
		const readyStatusClass = res.ready_for_job ? "ready" : "not-ready";
		const readyStatusText = res.ready_for_job ? "Job Ready" : "Gap Identified";

		let radialFgColorClass = "danger";
		if (res.ready_for_job) {
			radialFgColorClass = "ready";
		} else if (score >= 50) {
			radialFgColorClass = "warning";
		}

		detailsContainer.innerHTML = `
			<div class="skills-detail-container">
				<div class="gap-header-row">
					<div class="gap-readiness-box">
						<div class="gap-radial-container">
							<div class="gap-radial-bg"></div>
							<div class="gap-radial-fg ${radialFgColorClass}" style="--percent: ${score}%;"></div>
							<div class="gap-radial-text">${Math.round(score)}%</div>
						</div>
						<div>
							<div class="gap-status-title">Job Readiness Analysis</div>
							<div class="gap-status-desc">${res.matched_skill_count} of ${res.required_skill_count} required skills verified</div>
						</div>
					</div>
					<div>
						<span class="gap-badge-status ${readyStatusClass}">${readyStatusText}</span>
					</div>
				</div>

				<div class="mb-3">
					<div class="skills-detail-title">
						<i class="bi bi-patch-check-fill text-success"></i> Your Matched Skills
					</div>
					<div class="d-flex flex-wrap gap-2">
						${matchedTags || '<span class="skill-badge-empty">No matching skills found in the profile. Add more skills on the left to match.</span>'}
					</div>
				</div>

				<div class="skills-detail-title">
					<i class="bi bi-slash-circle text-warning"></i> Missing Skills to Acquire
				</div>

				<div class="row g-3">
					<div class="col-md-6 col-lg-3">
						<div class="skill-tier-card foundation-tier">
							<div class="tier-header">
								<i class="bi bi-mortarboard-fill text-primary"></i> Foundation
							</div>
							<div class="tier-body">
								${missingFoundationTags || '<span class="skill-badge-empty"><i class="bi bi-check2-circle text-success"></i> Mastered</span>'}
							</div>
						</div>
					</div>
					<div class="col-md-6 col-lg-3">
						<div class="skill-tier-card core-tier">
							<div class="tier-header">
								<i class="bi bi-code-slash text-indigo"></i> Core Domain
							</div>
							<div class="tier-body">
								${missingCoreDomainTags || '<span class="skill-badge-empty"><i class="bi bi-check2-circle text-success"></i> Mastered</span>'}
							</div>
						</div>
					</div>
					<div class="col-md-6 col-lg-3">
						<div class="skill-tier-card industry-tier">
							<div class="tier-header">
								<i class="bi bi-building text-violet"></i> Industry
							</div>
							<div class="tier-body">
								${missingIndustryTags || '<span class="skill-badge-empty"><i class="bi bi-check2-circle text-success"></i> Mastered</span>'}
							</div>
						</div>
					</div>
					<div class="col-md-6 col-lg-3">
						<div class="skill-tier-card emerging-tier">
							<div class="tier-header">
								<i class="bi bi-rocket-takeoff-fill text-success"></i> Emerging
							</div>
							<div class="tier-body">
								${missingEmergingTags || '<span class="skill-badge-empty"><i class="bi bi-check2-circle text-success"></i> Mastered</span>'}
							</div>
						</div>
					</div>
				</div>
			</div>
		`;
	}
});
