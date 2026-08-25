# -*- coding: utf-8 -*-
import frappe
import json
import logging
from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from frappe.utils import now_datetime

logger = logging.getLogger("frappe")

DOMAIN_SKILL_POINTS = {
    "javascript": [
        "Variables, Scope (var/let/const), and Data Types",
        "Control Flow, Loops, and Functions (including arrow functions)",
        "DOM Selection, Manipulation, and Event Handlers",
        "Asynchronous Javascript: Callbacks, Promises, and Async/Await",
        "API Integration using Fetch / Axios and handling JSON data",
        "ES6+ Features (Destructuring, Spread/Rest, Modules)",
        "Error Handling with Try/Catch and Debugging in DevTools"
    ],
    "python": [
        "Basic Syntax, variables, operators, and basic input/output",
        "Control flow (if-else, loops) and defining reusable functions",
        "Built-in data structures: Lists, Tuples, Dictionaries, and Sets",
        "File I/O operations and Exception Handling (try-except blocks)",
        "Object-Oriented Programming: Classes, Objects, Inheritance, and Methods",
        "Virtual environments, PIP package manager, and importing libraries"
    ],
    "git": [
        "Understanding version control concepts and setting up Git configurations",
        "Initializing repositories, tracking files, staging, and committing changes",
        "Creating, switching, merging, and deleting branches",
        "Resolving merge conflicts and inspecting commit logs (git log, git diff)",
        "Working with remotes (GitHub/GitLab): cloning, pushing, pulling, and PRs"
    ],
    "sql": [
        "Relational Database Concepts, schemas, tables, and data types",
        "Writing Basic SELECT queries with filtering (WHERE, LIKE, IN) and sorting",
        "Table Joins: INNER, LEFT, RIGHT, and FULL outer joins",
        "Aggregation functions (COUNT, SUM, AVG) and GROUP BY/HAVING clauses",
        "Subqueries, Common Table Expressions (CTEs), and nested SELECT statements",
        "Data Definition Language (CREATE, ALTER, DROP) and DML (INSERT, UPDATE, DELETE)"
    ],
    "pytorch": [
        "Introduction to Tensors: creation, operations, and CPU/GPU device handling",
        "Autograd: automatic differentiation and computing gradients",
        "Building Neural Networks using torch.nn module (Linear, Conv, Activation layers)",
        "Defining Loss Functions and Optimizers (torch.optim)",
        "Creating Dataset and DataLoader classes for custom data pipelines",
        "Writing the training and validation loops, tracking metrics, and saving models"
    ],
    "amazon web services": [
        "AWS Global Infrastructure: regions, availability zones, and VPC essentials",
        "Identity and Access Management (IAM): users, groups, roles, and policies",
        "Compute: launching and configuring EC2 instances and Security Groups",
        "Storage: using S3 buckets, object storage classes, and lifecycle policies",
        "Database: setting up RDS instances and basic DynamoDB tables",
        "Deployment: introduction to serverless with AWS Lambda and API Gateway"
    ],
    "aws": [
        "AWS Global Infrastructure: regions, availability zones, and VPC essentials",
        "Identity and Access Management (IAM): users, groups, roles, and policies",
        "Compute: launching and configuring EC2 instances and Security Groups",
        "Storage: using S3 buckets, object storage classes, and lifecycle policies",
        "Database: setting up RDS instances and basic DynamoDB tables",
        "Deployment: introduction to serverless with AWS Lambda and API Gateway"
    ],
    "deep learning": [
        "Foundations of Deep Learning: perceptrons, activation functions, and feedforward networks",
        "Backpropagation algorithm, gradient descent variants, and learning rate scheduling",
        "Regularization techniques: Dropout, Batch Normalization, and Weight Decay",
        "Convolutional Neural Networks (CNNs) for computer vision and image processing",
        "Recurrent Neural Networks (RNNs), LSTMs, and GRUs for sequential data",
        "Model evaluation: overfitting/underfitting diagnosis and hyperparameter tuning"
    ],
    "machine learning": [
        "Supervised vs Unsupervised learning paradigms and ML project lifecycles",
        "Data Preprocessing: handling missing values, encoding, and feature scaling",
        "Regression models: Linear and Logistic regression, and evaluation metrics",
        "Classification models: Decision Trees, Random Forests, SVMs, and Naive Bayes",
        "Clustering algorithms: K-Means, Hierarchical, and Dimensionality Reduction (PCA)",
        "Model validation: Train-Test splits, K-Fold Cross-Validation, and Bias-Variance trade-off"
    ],
    "linear algebra": [
        "Vectors: vector spaces, linear combinations, span, and linear independence",
        "Matrices: matrix multiplication, transpose, and solving systems of linear equations",
        "Matrix Determinants, Inverse matrices, and Rank of a matrix",
        "Eigenvalues and Eigenvectors: definitions, calculations, and properties",
        "Matrix decompositions: Singular Value Decomposition (SVD) and PCA applications"
    ],
    "statistics": [
        "Descriptive statistics: mean, median, mode, variance, and standard deviation",
        "Probability distributions: Normal, Binomial, Poisson, and Central Limit Theorem",
        "Inferential statistics: Hypothesis Testing, Z-test, T-test, and ANOVA",
        "P-values, confidence intervals, and Type I/II errors",
        "Correlation analysis and Simple Linear Regression model fitting"
    ],
    "tensorflow": [
        "TensorFlow basics: Constants, Variables, and basic tensor math operations",
        "Keras API: Sequential vs Functional API models construction",
        "Compiling models with optimizers, loss functions, and training metrics",
        "Model training using fit(), evaluating with evaluate(), and predicting with predict()",
        "TensorBoard integration for training visualization and monitoring",
        "Saving, exporting, and serving TensorFlow models (TF Serving / TF Lite)"
    ],
    "multi-agent frameworks": [
        "Conceptualizing Multi-Agent Systems: agents, environments, and communication",
        "Framework setup: CrewAI, AutoGen, or LangGraph installation and configuration",
        "Defining agents: roles, goals, backstories, and system instructions",
        "Creating custom Tools and binding them to agents for external execution",
        "Structuring tasks, sequential/hierarchical process flows, and delegation",
        "Running multi-agent execution, parsing final outputs, and error handling"
    ],
    "pandas": [
        "Pandas DataStructures: creating and manipulating Series and DataFrames",
        "Data import/export: CSV, Excel, SQL databases, and JSON formats",
        "Data cleaning: handling missing data, duplicates, and type conversions",
        "Indexing, selecting, filtering, and sorting DataFrame rows and columns",
        "Data Aggregation: GroupBy operations, pivot tables, and merging/joining datasets",
        "Time Series data handling and vectorised string/math operations"
    ],
    "numpy": [
        "NDArray creation: arrays, ranges, zeros, ones, and random generation",
        "Array indexing, slicing, multi-dimensional array access, and reshaping",
        "Vectorized math operations and Broadcasting rules across different shapes",
        "Statistical functions: mean, standard deviation, sum, min/max, and sorting",
        "Matrix multiplication, dot product, and linear algebra operations in NumPy",
        "Memory efficiency and array views vs copies"
    ],
    "autogpt": [
        "Understanding Autonomous AI Agent architectures and loop structures",
        "AutoGPT installation, environment variables configuration, and API keys setup",
        "Configuring agent goals, budget constraints, and continuous execution settings",
        "Analyzing agent memory backends (Local, Redis, Pinecone, Milvus)",
        "Monitoring workspace files, command executions, and self-correction loops"
    ],
    "power bi": [
        "Connecting to data sources (Files, Databases, Web) and using Power Query",
        "Data transformation: cleaning, column profiling, merging, and shaping",
        "Data modeling: active relationships, star schema design, and cardinality",
        "DAX calculations: calculated columns, measures, and time-intelligence functions",
        "Visualizations: creating interactive reports, charts, maps, and slicers",
        "Publishing to Power BI Service, configuring gateways, and scheduling refreshes"
    ],
    "tableau": [
        "Connecting to data files, databases, and defining relationships/joins",
        "Understanding Tableau terminology: dimensions vs measures, discrete vs continuous",
        "Building basic charts: bar charts, line graphs, scatter plots, and maps",
        "Calculated fields, table calculations, logical statements, and parameters",
        "Designing interactive dashboards, dashboard actions, and storyboards",
        "Sharing workbooks, exporting packages, and publishing to Tableau Public/Server"
    ],
    "natural language processing": [
        "Text Preprocessing: tokenization, stopword removal, stemming, and lemmatization",
        "Feature extraction: Bag of Words (BoW), TF-IDF, and N-grams",
        "Word Embeddings: Word2Vec, GloVe, and FastText vector representations",
        "Sequence Modeling: Part-of-Speech (POS) tagging and Named Entity Recognition (NER)",
        "Transformers: self-attention mechanisms, BERT, and GPT architectures",
        "NLP Tasks: Text Classification, Sentiment Analysis, and Machine Translation"
    ],
    "nlp": [
        "Text Preprocessing: tokenization, stopword removal, stemming, and lemmatization",
        "Feature extraction: Bag of Words (BoW), TF-IDF, and N-grams",
        "Word Embeddings: Word2Vec, GloVe, and FastText vector representations",
        "Sequence Modeling: Part-of-Speech (POS) tagging and Named Entity Recognition (NER)",
        "Transformers: self-attention mechanisms, BERT, and GPT architectures",
        "NLP Tasks: Text Classification, Sentiment Analysis, and Machine Translation"
    ],
    "neural networks": [
        "Biological neuron analogy and artificial neuron mathematical models",
        "Activation functions: Sigmoid, Tanh, ReLU, Leaky ReLU, and Softmax",
        "Feedforward architectures and layer structures (input, hidden, output)",
        "Forward propagation matrix calculations and computing loss/cost functions",
        "Backpropagation math: chain rule of calculus and gradient descent optimization",
        "Mitigating exploding/vanishing gradients and weight initialization strategies"
    ],
    "azure": [
        "Azure architecture: resource groups, regions, availability zones, and subscriptions",
        "Azure Active Directory (Azure AD) users, roles, and identity protection",
        "Compute: virtual machines deployment, scaling, and App Services",
        "Networking: Azure Virtual Networks (VNets), subnets, and Network Security Groups",
        "Storage: Azure Blob Storage, File storage, and Disk storage configurations",
        "Azure SQL Database, Cosmos DB setup, and basic deployment resources"
    ],
    "google cloud platform": [
        "GCP resource hierarchy: organizations, folders, projects, and billing",
        "Identity & Access Management (IAM) members, roles, and Service Accounts",
        "Compute: Compute Engine VMs, App Engine applications, and Cloud Functions",
        "Storage: Cloud Storage buckets, storage classes, and bucket policies",
        "Databases: Cloud SQL instances, Cloud Spanner, and BigQuery setup",
        "Networking: VPC networks, subnets, firewall rules, and Cloud DNS"
    ],
    "gcp": [
        "GCP resource hierarchy: organizations, folders, projects, and billing",
        "Identity & Access Management (IAM) members, roles, and Service Accounts",
        "Compute: Compute Engine VMs, App Engine applications, and Cloud Functions",
        "Storage: Cloud Storage buckets, storage classes, and bucket policies",
        "Databases: Cloud SQL instances, Cloud Spanner, and BigQuery setup",
        "Networking: VPC networks, subnets, firewall rules, and Cloud DNS"
    ],
    "ai-assisted development": [
        "Setting up AI coding assistants (GitHub Copilot, Cursor, Tabnine)",
        "Effective prompting for code generation, refactoring, and test writing",
        "Using AI for explaining complex codebases and translating code between languages",
        "Validating AI-generated code: safety checks, syntax validation, and unit tests",
        "Integrating AI toolchains into daily IDE workflows and version control practices"
    ],
    "webassembly": [
        "WebAssembly (Wasm) architecture, binary format, and text format (.wat)",
        "Setting up compilation toolchains (Emscripten for C/C++, wasm-pack for Rust)",
        "Writing code in high-performance languages and compiling to .wasm",
        "Loading and instantiating WebAssembly modules in JavaScript",
        "Managing the WebAssembly memory buffer and data sharing with JavaScript",
        "Optimizing WebAssembly module size and runtime performance"
    ],
    "wasm": [
        "WebAssembly (Wasm) architecture, binary format, and text format (.wat)",
        "Setting up compilation toolchains (Emscripten for C/C++, wasm-pack for Rust)",
        "Writing code in high-performance languages and compiling to .wasm",
        "Loading and instantiating WebAssembly modules in JavaScript",
        "Managing the WebAssembly memory buffer and data sharing with JavaScript",
        "Optimizing WebAssembly module size and runtime performance"
    ],
    "edge computing": [
        "Edge computing paradigm vs traditional centralized cloud computing",
        "Edge hardware concepts: IoT gateways, sensors, and micro-controllers",
        "Deploying workloads to the edge: Docker containerization for edge devices",
        "Communication protocols: MQTT, CoAP, and HTTP/REST at the edge",
        "Data filtering and offline capability in edge applications",
        "Security, device updates, and remote monitoring of edge nodes"
    ],
    "react": [
        "React core concepts: Virtual DOM, components, props, and JSX syntax",
        "State Management: useState, useReducer, and Context API",
        "Component Lifecycle & Side Effects using useEffect and custom Hooks",
        "React Router for declarative routing and URL parameter navigation",
        "Performance optimization: React.memo, useMemo, and useCallback Hooks",
        "Handling Forms, validation, and integrating with REST/GraphQL APIs"
    ]
}

def get_domain_milestone_points(skill_name):
    clean_name = str(skill_name or "").lower().strip()
    if clean_name in DOMAIN_SKILL_POINTS:
        return DOMAIN_SKILL_POINTS[clean_name]
    
    # Generic but structured step-by-step roadmap points for any other skill
    return [
        f"Fundamentals: Core concepts, terminology, and setup for {skill_name}",
        f"Hands-on Practice: Building initial exercises and basic features in {skill_name}",
        f"Intermediate Techniques: Advanced configurations, patterns, and structure of {skill_name}",
        f"Project Application: Integrating {skill_name} into a realistic domain project",
        f"Testing & Verification: Benchmarking, debugging, and refining {skill_name} outcomes"
    ]

def generate_personalized_roadmap(enrollment_name):
	"""
	Background worker task to generate AI roadmap template if missing,
	then personalize it and activate the student path enrollment.
	"""
	# Reconnect to DB to prevent idle timeout issues
	if not frappe.flags.in_test:
		try:
			frappe.db.close()
			frappe.db.connect()
		except Exception:
			pass

	if not frappe.db.exists("Student Path Enrollment", enrollment_name):
		return

	doc = frappe.get_doc("Student Path Enrollment", enrollment_name)
	student = doc.student
	career_path = doc.career_path

	# Step 1: Ensure Roadmap Template exists. If not, generate generic template via LLM.
	if not frappe.db.exists("Roadmap Template", career_path):
		agent = RoadmapAgent()
		try:
			# Generate generic template roadmap (student="Generic")
			result = agent.run("Generic", career_path)
		except Exception as e:
			frappe.log_error(f"AI Roadmap background task error during generic template generation: {str(e)}", "AI Roadmap Generation")
			_pause_enrollment(enrollment_name)
			return

		if result.validation_status != "Valid":
			frappe.log_error(f"AI Roadmap background validation failed for generic template: {result.error_message}", "AI Roadmap Generation")
			_pause_enrollment(enrollment_name)
			return

		# Save to Roadmap Template
		try:
			if not frappe.flags.in_test:
				try:
					frappe.db.close()
					frappe.db.connect()
				except Exception:
					pass
			roadmap_dict = result.roadmap.to_dict()
			template_doc = frappe.get_doc({
				"doctype": "Roadmap Template",
				"career_path": career_path,
				"roadmap_version": "1.0",
				"milestones_json": json.dumps(roadmap_dict)
			})
			template_doc.insert(ignore_permissions=True)
			frappe.db.commit()
		except (frappe.exceptions.DuplicateEntryError, frappe.exceptions.LinkExistsError):
			# Another worker already saved this template concurrently (race condition).
			# This is safe — both workers generated valid roadmaps and we only need one.
			# Continue to personalization using the already-persisted template.
			frappe.db.rollback()
			logger.warning(
				"Roadmap Template for '%s' already exists (concurrent insert) — "
				"reusing the existing template.",
				career_path
			)
		except Exception as save_err:
			frappe.log_error(f"Failed to save generic Roadmap Template: {str(save_err)}", "AI Roadmap Generation")
			_pause_enrollment(enrollment_name)
			return

	# Step 2: Reload enrollment document and personalize it from Roadmap Template
	doc = frappe.get_doc("Student Path Enrollment", enrollment_name)

	try:
		personalize_enrollment_from_template(doc)
		doc.status = "Active"
		doc.ai_recommended = 1

		from nexedu.path_finder.utils.milestone_engine import recalculate_all_milestones
		recalculate_all_milestones(doc)

		doc.save(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to personalize and activate enrollment: {str(e)}", "AI Roadmap Generation")
		_pause_enrollment(enrollment_name)
		return


def _pause_enrollment(enrollment_name):
	try:
		doc = frappe.get_doc("Student Path Enrollment", enrollment_name)
		doc.status = "Paused"
		doc.ai_recommended = 0
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		pass


def personalize_enrollment_from_template(doc):
	"""
	Personalizes enrollment document using the generic Roadmap Template.
	"""
	template_doc = frappe.get_doc("Roadmap Template", doc.career_path)
	milestones_data = json.loads(template_doc.milestones_json)
	if isinstance(milestones_data, dict):
		milestones_list = milestones_data.get("milestones", [])
	else:
		milestones_list = milestones_data
	personalize_roadmap_for_student(doc, milestones_list)


def personalize_roadmap_for_student(enrollment_doc, milestones_list):
	"""
	Applies the student's skill gap report to filter the generic milestones list
	and creates the personalized child progress rows.
	"""
	student = enrollment_doc.student
	career_path = enrollment_doc.career_path

	# Get student's verified skills
	student_skill_map = {}
	if student:
		student_skills = frappe.get_all(
			"Student Skill",
			filters={"student": student},
			fields=["skill", "current_level", "status"],
		)
		student_skill_map = {s.skill: s for s in student_skills}

	# Helper function for skill rank
	def level_rank(lvl):
		ranks = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}
		return ranks.get(lvl or "Beginner", 1)

	type_mapping = {
		"Course": "Courses",
		"Assessment": "Assessment",
		"Project": "Project",
		"Internship": "Internship",
		"Mentor Session": "Mentor Session Booking"
	}

	# Resolve skill levels map from the Career Path (if it exists)
	skill_levels_map = {}
	prereq_skills_list = []
	if frappe.db.exists("Career Path", career_path):
		prereqs = frappe.get_all(
			"Prerequisite Skills",
			filters={"parent": career_path, "parentfield": "prerequisite_skills"},
			fields=["prerequisite_skills", "level"]
		)
		for p in prereqs:
			if p.prerequisite_skills and p.level:
				skill_levels_map[p.prerequisite_skills] = p.level
				prereq_skills_list.append(p.prerequisite_skills)

		milestones_std = frappe.get_all(
			"Path Milestone",
			filters={"parent": career_path, "parentfield": "path_milestone"},
			fields=["skill", "required_skill_level"]
		)
		for m_std in milestones_std:
			if m_std.skill and m_std.required_skill_level:
				skill_levels_map[m_std.skill] = m_std.required_skill_level

	milestones_progress = []
	milestone_points = []
	seen_skills = set()

	# Sequence counter for remaining milestones
	seq_counter = 1

	for m in milestones_list:
		title = m.get("title")
		m_type = m.get("type")
		skill = m.get("primary_skill") or m.get("skill")
		if skill:
			skill_key = skill.lower().strip()
			if skill_key in seen_skills:
				continue
			seen_skills.add(skill_key)
		skill_tier = m.get("skill_tier")
		duration_days = m.get("duration_days") or 14
		objective = m.get("objective")
		project = m.get("project")
		points = m.get("points") or []
		# Overwrite generic/empty points with high quality domain-specific step-by-step roadmap points
		is_generic = False
		if not points:
			is_generic = True
		elif len(points) == 5 and any("Introduction to" in str(p) and "and setup" in str(p) for p in points):
			is_generic = True
		
		if is_generic and skill:
			points = get_domain_milestone_points(skill)
		linked_resource_type = m.get("linked_resource_type")
		linked_resource = m.get("linked_resource")

		# Ensure skill categories/skills exist in system
		if skill and not frappe.db.exists("Skill", skill):
			try:
				frappe.get_doc({"doctype": "Skill", "skill_name": skill}).insert(ignore_permissions=True)
			except Exception:
				pass
		if skill_tier and not frappe.db.exists("Skill Category", skill_tier):
			try:
				frappe.get_doc({"doctype": "Skill Category", "category_name": skill_tier}).insert(ignore_permissions=True)
			except Exception:
				pass

		ref_doctype = None
		linked_res = None
		if linked_resource_type:
			mapped = type_mapping.get(linked_resource_type)
			if mapped and frappe.db.exists("DocType", mapped):
				ref_doctype = mapped
			elif frappe.db.exists("DocType", linked_resource_type):
				ref_doctype = linked_resource_type

			if ref_doctype and linked_resource:
				if frappe.db.exists(ref_doctype, linked_resource):
					linked_res = linked_resource
				else:
					ref_doctype = None
					linked_res = None

		req_level = skill_levels_map.get(skill) or "Beginner"
		is_prereq = 0
		if skill_tier == "Foundation" or (skill and skill in prereq_skills_list):
			is_prereq = 1

		student_entry = student_skill_map.get(skill) if skill else None
		already_has = (
			student_entry
			and skill
			and level_rank(student_entry.current_level) >= level_rank(req_level)
		)
		is_verified = bool(student_entry and student_entry.get("status") == "Verified")

		status = "Completed" if already_has and is_verified else "Not Started"
		is_auto_skip = 1 if already_has and is_verified else 0
		completed_at = now_datetime() if is_auto_skip else None
		score = 100 if is_auto_skip else None
		ai_feedback = "Skill already verified — auto-completed." if is_auto_skip else None

		res_type = linked_resource_type
		if res_type not in ["Course", "Assessment", "Project", "Internship", "Mentor Session"]:
			res_type = ""

		milestones_progress.append({
			"doctype": "Student Milestone Progress",
			"milestone_title": title,
			"milestone_order": seq_counter,
			"milestone_type": m_type,
			"skill": skill,
			"required_skill_level": req_level,
			"is_prereq": is_prereq,
			"skill_tier": skill_tier,
			"category": skill_tier,
			"duration_days": duration_days,
			"objective": objective,
			"project": project,
			"linked_resource_type": res_type,
			"reference_doctype": ref_doctype,
			"linked_resource": linked_res,
			"status": status,
			"is_auto_skipped": is_auto_skip,
			"completed_at": completed_at,
			"score": score,
			"ai_feedback": ai_feedback
		})

		point_status = "Not Started"
		for pt in points:
			milestone_points.append({
				"doctype": "Student Milestone Point",
				"milestone_title": title,
				"point_title": pt,
				"status": point_status
			})

		seq_counter += 1

	enrollment_doc.milestone_progress = []
	for mp in milestones_progress:
		enrollment_doc.append("milestone_progress", mp)

	enrollment_doc.milestone_points = []
	for pt in milestone_points:
		enrollment_doc.append("milestone_points", pt)
