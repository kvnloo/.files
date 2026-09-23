# Advanced Prompt Engineering for LLM Self-Improvement in Web Design

**Research Date**: 2026-02-06
**Confidence Level**: High (0.85) - Based on 30+ sources including academic papers, official documentation, and practitioner guides
**Focus**: Concrete prompt templates and patterns applicable to a web design agent

---

## Table of Contents

1. [Constitutional AI - Self-Alignment Through Principles](#1-constitutional-ai)
2. [Self-Instruct - Generating Training Data](#2-self-instruct)
3. [Chain of Thought Variations for Self-Improvement](#3-chain-of-thought-variations)
4. [Tree of Thoughts](#4-tree-of-thoughts)
5. [Graph of Thoughts](#5-graph-of-thoughts)
6. [Prompt Chaining for Iterative Improvement](#6-prompt-chaining)
7. [Meta-Prompting](#7-meta-prompting)
8. [Honest Self-Assessment Prompts](#8-honest-self-assessment)
9. [Persona-Based Prompting](#9-persona-based-prompting)
10. [Few-Shot Learning from Stored Examples](#10-few-shot-learning)
11. [Synthesis: Web Design Agent Self-Improvement System](#11-synthesis)

---

## 1. Constitutional AI

**Core Mechanism**: The model critiques and revises its own outputs against an explicit set of principles ("constitution"), replacing human feedback with self-generated alignment feedback.

**Key Insight for Web Design**: Define a "design constitution" - a set of principles the agent evaluates its own output against after generation.

### Web Design Constitution Template

```
DESIGN CONSTITUTION

You must evaluate your generated design against these principles:

ACCESSIBILITY PRINCIPLES:
1. All text must have sufficient contrast ratio (WCAG AA minimum: 4.5:1 for normal text, 3:1 for large text)
2. Interactive elements must have clear focus states
3. The design must be navigable by keyboard alone
4. All images must have meaningful alt text or be marked decorative

VISUAL HIERARCHY PRINCIPLES:
5. There must be exactly one primary visual focal point per viewport
6. Heading levels must follow a logical descending order
7. Whitespace must create clear content groupings (Gestalt proximity)
8. Color must not be the sole means of conveying information

LAYOUT PRINCIPLES:
9. The layout must be responsive across mobile (320px), tablet (768px), and desktop (1280px)
10. No horizontal scrolling at any standard breakpoint
11. Touch targets must be at least 44x44px on mobile
12. Content reading order must match visual order

PERFORMANCE PRINCIPLES:
13. Avoid layout shifts caused by unspecified image dimensions
14. Minimize render-blocking resources
15. Prefer CSS over JavaScript for visual effects

SELF-CRITIQUE INSTRUCTION:
After generating a design, review it against each principle above.
For each violation found:
- State which principle is violated
- Explain the specific violation
- Provide the corrected code
Then output the revised design.
```

### Constitutional Self-Critique Loop

```
Step 1 - GENERATE: Create the initial design based on the user request.

Step 2 - CRITIQUE: Review the design against the constitution.
"Examine your generated HTML/CSS against each design principle.
List every violation you find. Be thorough and honest.
Format: [PRINCIPLE N]: [VIOLATION DESCRIPTION] -> [FIX]"

Step 3 - REVISE: Apply all fixes and output the corrected design.
"Now generate a revised version that addresses every violation
identified in your critique. Show only the final corrected code."

Step 4 - VERIFY: Confirm the revision resolved all issues.
"Re-examine the revised design. Are there any remaining violations?
If yes, repeat the fix. If no, confirm compliance."
```

---

## 2. Self-Instruct

**Core Mechanism**: The model generates its own training examples (instruction, input, output triples) from a small seed set, then uses these to improve itself. The original paper demonstrated a 33% absolute improvement on SuperNaturalInstructions.

**Key Insight for Web Design**: Generate a library of design tasks and ideal solutions that the agent can reference as few-shot examples in future sessions.

### Self-Instruct Template for Web Design

```
SEED TASK SET (5 examples to bootstrap from):

Task 1: "Create a responsive navigation bar with logo, links, and mobile hamburger menu"
Input: Brand name "TechFlow", links: Home, Features, Pricing, Contact
Output: [Complete HTML/CSS with hamburger toggle, sticky behavior, accessible markup]

Task 2: "Design a hero section with headline, subtext, and CTA button"
Input: SaaS product for project management, dark theme
Output: [Complete hero with gradient background, clear hierarchy, animated CTA]

Task 3: "Build a pricing comparison table with three tiers"
Input: Free/Pro/Enterprise, highlight Pro as recommended
Output: [Responsive card grid with visual emphasis on recommended tier]

Task 4: "Create a testimonial carousel section"
Input: 4 testimonials with photos, names, roles
Output: [Accessible carousel with dots, swipe support, auto-play with pause]

Task 5: "Design a footer with newsletter signup, links, and social icons"
Input: 4 link columns, newsletter form, social media links
Output: [Responsive footer with proper semantic structure]

GENERATION INSTRUCTION:
Based on the seed tasks above, generate 10 new web design tasks that:
1. Cover different UI components not in the seed set
2. Vary in complexity (simple component to full section)
3. Include specific constraints (accessibility, animation, dark mode, etc.)
4. Provide realistic input parameters
5. Each task must be distinct from all others

For each generated task, also produce the ideal output following
these quality criteria:
- Semantic HTML5
- Modern CSS (Grid/Flexbox, custom properties)
- Mobile-first responsive design
- WCAG AA accessible
- Performance-optimized
```

### Bootstrapping Loop

```
ROUND 1: Generate 10 tasks from seed set -> Filter for quality -> Add to task pool
ROUND 2: Sample from expanded pool -> Generate 10 more tasks -> Filter -> Add
ROUND 3: Sample diversely from full pool -> Generate 10 more -> Filter -> Add

QUALITY FILTER:
Reject generated tasks that:
- Are too similar to existing tasks (cosine similarity > 0.7)
- Have outputs with HTML validation errors
- Lack responsive design
- Miss accessibility basics
- Are trivially simple (< 20 lines of meaningful code)
```

---

## 3. Chain of Thought Variations for Self-Improvement

### 3a. Self-Refine (Iterative Critique-Revision)

**Core Mechanism**: Generate -> Critique -> Revise in a loop. Research shows self-refinement cut code errors by 30% in benchmarks.

```
SELF-REFINE TEMPLATE FOR WEB DESIGN:

=== STEP 1: INITIAL GENERATION ===
[Generate the design based on user requirements]

=== STEP 2: SELF-FEEDBACK ===
Review the design you just created. Evaluate on these axes:

VISUAL QUALITY (1-10):
- Color harmony and contrast: ___
- Typography hierarchy and readability: ___
- Spacing consistency and rhythm: ___
- Visual balance and alignment: ___

TECHNICAL QUALITY (1-10):
- Semantic HTML correctness: ___
- CSS efficiency (no redundancy): ___
- Responsive behavior: ___
- Accessibility compliance: ___

DESIGN EFFECTIVENESS (1-10):
- Does it solve the user's stated problem? ___
- Is the information hierarchy clear? ___
- Are interactive affordances obvious? ___
- Does it follow established UI patterns? ___

For any score below 7, explain specifically what is wrong
and how to fix it.

=== STEP 3: REFINEMENT ===
Based on your feedback, generate an improved version that
addresses every issue scored below 7. Explain each change made.

=== STEP 4: FINAL CHECK ===
Re-score the improved version. If any axis is still below 7,
repeat steps 2-3. Maximum 3 iterations.
```

### 3b. Reflexion (Learning from Mistakes Across Attempts)

**Core Mechanism**: Convert environmental feedback into linguistic self-reflection stored in memory for future attempts. Uses Actor-Evaluator-Reflector architecture.

```
REFLEXION TEMPLATE FOR WEB DESIGN:

=== ACTOR (Generate) ===
Create the design component as requested.

=== EVALUATOR (Score) ===
Test the output against these binary criteria:
[ ] HTML validates without errors
[ ] Passes axe-core accessibility check
[ ] Renders correctly at 320px, 768px, 1280px
[ ] All interactive states are defined (hover, focus, active, disabled)
[ ] Load performance: no layout shifts, optimized images
[ ] Matches user's stated requirements
Score: [passed] / [total]

=== REFLECTOR (Learn) ===
If score < 100%:
"In my previous attempt, I failed on: [list failures].
The root causes were: [analysis].
In my next attempt, I will specifically: [concrete changes].
I should remember: [generalizable lesson]."

=== MEMORY (Persist) ===
Store the reflection for use in future design tasks:
{
  "task_type": "navigation_bar",
  "lesson": "Always include aria-expanded on hamburger toggles",
  "failure_mode": "Missing ARIA state for mobile menu toggle",
  "prevention": "Checklist item: verify all toggle elements have aria-expanded"
}
```

### 3c. Critic-CoT (Slow Analytic Self-Critique)

```
CRITIC-COT TEMPLATE:

After generating a design, engage in slow, deliberate critique:

"Let me carefully examine this design step by step.

STEP 1 - Structure Analysis:
I will trace through the DOM tree and verify semantic correctness...
[Detailed analysis]

STEP 2 - Visual Flow Analysis:
I will follow the user's likely eye path through this layout...
[Detailed analysis]

STEP 3 - Interaction Analysis:
I will mentally simulate each user interaction...
[Detailed analysis]

STEP 4 - Edge Case Analysis:
I will consider what happens with: very long text, missing images,
slow network, screen reader, keyboard-only navigation...
[Detailed analysis]

STEP 5 - Verdict:
Based on this analysis, the following changes are needed:
[Prioritized list of improvements]"
```

### 3d. Reversing Chain-of-Thought (RCoT) for Design

```
RCOT TEMPLATE FOR DETECTING DESIGN HALLUCINATIONS:

Step 1: Generate the design from the user's requirements.

Step 2: From the generated design ALONE (without looking at
the original requirements), describe what this design is for:
"Looking at this HTML/CSS, this appears to be a design for..."

Step 3: Compare the reconstructed description with the original
requirements. List any discrepancies:
- Features in the requirements but missing from the design
- Features in the design not requested by the user
- Misinterpretations of the requirements

Step 4: Fix all discrepancies found in Step 3.
```

---

## 4. Tree of Thoughts

**Core Mechanism**: Explore multiple design approaches in parallel, evaluate each, and select the best path. Unlike linear CoT, ToT enables backtracking and comparison.

### Tree of Thoughts for Design Exploration

```
TREE OF THOUGHTS TEMPLATE:

USER REQUEST: [Design requirement]

=== THOUGHT GENERATION (Breadth-First) ===

APPROACH A - [e.g., Card-based layout]:
"This approach uses... because..."
[Sketch key structural decisions]

APPROACH B - [e.g., List-based layout]:
"This approach uses... because..."
[Sketch key structural decisions]

APPROACH C - [e.g., Dashboard grid layout]:
"This approach uses... because..."
[Sketch key structural decisions]

=== THOUGHT EVALUATION ===

Rate each approach (sure / maybe / impossible):

APPROACH A:
- Meets requirements? [sure/maybe/impossible]
- Responsive feasibility? [sure/maybe/impossible]
- Accessibility? [sure/maybe/impossible]
- Implementation complexity? [sure/maybe/impossible]
- User experience quality? [sure/maybe/impossible]

[Repeat for B and C]

=== SELECTION & DEEPENING ===

Best approach: [Selected approach with justification]
Now deepen this approach with specific implementation decisions...

For each sub-decision (color scheme, typography, spacing system),
repeat the generate-evaluate-select cycle.
```

### Simplified Multi-Expert ToT (Hulbert Variant)

```
"Imagine three expert web designers are independently designing
this component. Each will share their approach step by step.

DESIGNER 1 (Minimalist specialist):
Step 1: [Their first structural decision]

DESIGNER 2 (Interaction design specialist):
Step 1: [Their first structural decision]

DESIGNER 3 (Accessibility specialist):
Step 1: [Their first structural decision]

All designers review each other's Step 1 and continue to Step 2.
If any designer realizes their approach has a fundamental flaw,
they withdraw and explain why.

Continue until one approach emerges as clearly superior, or
synthesize the best elements from each surviving approach."
```

---

## 5. Graph of Thoughts

**Core Mechanism**: Model reasoning as an arbitrary graph (not just a tree), enabling combination of thoughts, feedback loops, and thought refinement. GoT improved quality by 62% over ToT while reducing costs by 31%.

### Graph of Thoughts for Complex Design Systems

```
GRAPH OF THOUGHTS TEMPLATE:

=== DECOMPOSITION (Split into thought vertices) ===

THOUGHT 1 - Layout Structure: [Grid/flex decisions]
THOUGHT 2 - Color System: [Palette and application rules]
THOUGHT 3 - Typography Scale: [Font sizes, weights, line heights]
THOUGHT 4 - Component Patterns: [Reusable component definitions]
THOUGHT 5 - Responsive Strategy: [Breakpoints and adaptations]
THOUGHT 6 - Interaction Design: [States, transitions, feedback]
THOUGHT 7 - Accessibility Layer: [ARIA, keyboard, screen reader]

=== AGGREGATION (Combine related thoughts) ===

COMBINED A (Thoughts 1+5): Layout + Responsive
"How does the layout structure adapt across breakpoints?
Ensure the grid system and responsive strategy are coherent..."

COMBINED B (Thoughts 2+3): Visual Language
"Do the colors and typography work together harmoniously?
Check contrast ratios with the specific font sizes chosen..."

COMBINED C (Thoughts 4+6+7): Interactive Components
"Are the component patterns accessible and interactive?
Verify each component has proper states and ARIA..."

=== REFINEMENT (Feedback loops) ===

Take COMBINED A and refine it using insights from COMBINED B:
"Now that we know the color system and typography, does the
responsive layout properly handle text reflow and color
in different contexts?"

=== SYNTHESIS (Final integration) ===

Merge all refined combinations into the final design,
checking for coherence across all dimensions.
```

---

## 6. Prompt Chaining for Iterative Improvement

**Core Mechanism**: Link multiple prompts where each output feeds the next. Research shows up to 15.6% better accuracy than monolithic prompts.

### Design Generation Pipeline

```
CHAIN 1 - REQUIREMENTS ANALYSIS:
Input: Raw user request
Prompt: "Parse this design request into structured requirements:
  - Component type:
  - Content elements:
  - Style preferences:
  - Functional requirements:
  - Constraints:
  - Target audience:
  - Responsive needs:"
Output -> feeds Chain 2

CHAIN 2 - STRUCTURAL DESIGN:
Input: Structured requirements from Chain 1
Prompt: "Generate semantic HTML structure for these requirements.
  Focus ONLY on structure, not styling. Use proper HTML5 elements.
  Include all ARIA attributes needed."
Output -> feeds Chain 3

CHAIN 3 - VISUAL DESIGN:
Input: HTML structure from Chain 2
Prompt: "Add CSS styling to this HTML structure.
  Apply: color scheme, typography, spacing, layout (Grid/Flexbox).
  Ensure responsive behavior with mobile-first approach.
  Use CSS custom properties for theming."
Output -> feeds Chain 4

CHAIN 4 - INTERACTION LAYER:
Input: Styled HTML from Chain 3
Prompt: "Add interactive behavior:
  - Hover/focus/active states for all interactive elements
  - Transitions and micro-animations
  - JavaScript for dynamic behavior (if needed)
  - Loading states and error states"
Output -> feeds Chain 5

CHAIN 5 - QUALITY REVIEW:
Input: Complete design from Chain 4
Prompt: "Review this complete design for:
  - Accessibility (WCAG AA)
  - Performance (render blocking, layout shifts)
  - Responsiveness (320px to 1920px)
  - Code quality (semantic, maintainable, DRY)
  List all issues found and fix them."
Output -> Final design
```

### Iterative Refinement Chain

```
REFINEMENT LOOP:

DRAFT -> CRITIQUE -> REVISE -> CRITIQUE -> FINALIZE

Draft Prompt:
"Create a [component] with [requirements]."

Critique Prompt:
"You are a senior design reviewer. Evaluate this design on:
1. Does it solve the user's problem effectively?
2. Is the visual hierarchy clear and purposeful?
3. Are there any usability concerns?
4. Is the code clean and maintainable?
5. What would a user struggle with?
Provide specific, actionable feedback."

Revise Prompt:
"Apply these specific improvements to the design:
[Critique output]
Show the complete revised code with comments
explaining each change."

Finalize Prompt:
"Perform final polish:
- Smooth all transitions
- Verify all edge cases
- Optimize any redundant code
- Add helpful code comments
Output the production-ready version."
```

---

## 7. Meta-Prompting

**Core Mechanism**: Use the LLM itself to generate, evaluate, and improve its own prompts. DSPy raised accuracy from 46.2% to 64.0% through programmatic prompt optimization.

### Meta-Prompt for Design Prompt Improvement

```
META-PROMPT TEMPLATE:

You are a prompt engineering expert specializing in web design tasks.

Given this simple design prompt:
"[ORIGINAL_PROMPT]"

Improve it by applying these prompt engineering best practices:

1. SPECIFICITY: Add concrete details about expected output format,
   quality standards, and technical requirements.

2. STRUCTURE: Break the task into clear sections with labeled
   outputs for each phase.

3. CONSTRAINTS: Add explicit constraints for accessibility,
   performance, responsiveness, and browser compatibility.

4. EXAMPLES: If helpful, include a brief example of the expected
   output format or quality level.

5. EVALUATION CRITERIA: Include self-assessment criteria the model
   should check its output against.

6. ROLE DEFINITION: Specify the expertise level and perspective
   the model should adopt.

Output the improved prompt. It should produce significantly
better web design output than the original.
```

### Recursive Meta-Prompting (Self-Optimizing)

```
LEVEL 1 - Generate initial design prompt for a task
LEVEL 2 - Use meta-prompt to improve the design prompt
LEVEL 3 - Use meta-prompt to improve the meta-prompt itself

SELF-OPTIMIZING META-PROMPT:

"Review the meta-prompt you just used to improve design prompts.
Evaluate its effectiveness:

1. Did it produce a measurably better design prompt?
2. What aspects of prompt improvement did it miss?
3. What additional techniques could it incorporate?
4. Is there unnecessary complexity that should be removed?

Now generate an improved version of the meta-prompt itself,
incorporating these insights. The improved meta-prompt should
produce even better design prompts on the next iteration."
```

### Contrastive Meta-Prompting (Learning from Failures)

```
CONTRASTIVE TEMPLATE:

Here are two designs generated from different prompts for the
same requirement:

DESIGN A (from simple prompt): [output]
DESIGN B (from detailed prompt): [output]

Analyze the differences:
1. What specific improvements does Design B have?
2. What prompt elements caused those improvements?
3. What additional prompt elements could improve further?
4. Extract generalizable rules about what makes effective
   design prompts.

Rules discovered:
- [Rule 1]
- [Rule 2]
- [Rule N]

Apply these rules to generate an even better prompt.
```

---

## 8. Honest Self-Assessment Prompts

**Key Research Finding**: Self-Calibration, Self-Verification, and Chain-of-Verification are the most effective patterns. The WebDevJudge rubric tree (intention, static quality, dynamic behavior) provides a web-specific evaluation framework.

### Design Self-Assessment Rubric

```
HONEST SELF-ASSESSMENT TEMPLATE:

After generating a design, evaluate it honestly using this rubric.
Rate each criterion 1-5. Do NOT inflate scores.
A score of 3 means "acceptable but not notable."
A score of 5 means "genuinely excellent, would impress a senior designer."

VISUAL DESIGN:
[ ] Color harmony (1-5): ___
    1=clashing 2=basic 3=acceptable 4=polished 5=distinctive
[ ] Typography (1-5): ___
    1=default/ugly 2=functional 3=readable 4=well-crafted 5=exceptional
[ ] Spacing/rhythm (1-5): ___
    1=cramped/scattered 2=uneven 3=adequate 4=consistent 5=precise
[ ] Visual hierarchy (1-5): ___
    1=flat 2=unclear 3=adequate 4=clear 5=compelling

TECHNICAL QUALITY:
[ ] Semantic HTML (1-5): ___
    1=div soup 2=some semantics 3=mostly correct 4=fully semantic 5=exemplary
[ ] CSS quality (1-5): ___
    1=inline/messy 2=functional 3=organized 4=efficient 5=elegant
[ ] Responsive design (1-5): ___
    1=broken 2=basic 3=functional 4=smooth 5=polished
[ ] Accessibility (1-5): ___
    1=inaccessible 2=basic 3=AA partial 4=AA compliant 5=AAA

UX QUALITY:
[ ] Clarity of purpose (1-5): ___
[ ] Ease of use (1-5): ___
[ ] Error handling (1-5): ___
[ ] Loading/empty states (1-5): ___

HONEST REFLECTION:
- What am I most uncertain about in this design?
- What would a professional designer criticize first?
- What did I take a shortcut on?
- If I had more time, what would I improve?

OVERALL CONFIDENCE: ___% (be honest, not optimistic)
```

### Self-Calibration for Design Decisions

```
SELF-CALIBRATION TEMPLATE:

For each design decision made, assess your confidence:

DECISION: [e.g., "Used a 12-column grid"]
CONFIDENCE: [high/medium/low]
REASONING: [Why this choice]
ALTERNATIVE: [What else could work]
RISK: [What could go wrong with this choice]
WOULD RECONSIDER IF: [Conditions that would change this decision]

Aggregate confidence assessment:
- Decisions with HIGH confidence: N
- Decisions with MEDIUM confidence: N
- Decisions with LOW confidence: N

If >30% of decisions are LOW confidence, flag for review.
```

### UICrit-Inspired Design Critique

```
DESIGN CRITIQUE TEMPLATE (Based on UICrit framework):

Evaluate the design using Sadler's critique format for each issue:

ISSUE FORMAT:
1. EXPECTED STANDARD: What good design looks like for this aspect
2. CURRENT GAP: How the design falls short of that standard
3. REMEDIATION: Specific action to close the gap

CRITIQUE CATEGORIES:
- LAYOUT: Positioning, alignment, visual hierarchy, grouping, simplicity
- COLOR CONTRAST: Text/background ratios, icon visibility, button contrast
- TEXT READABILITY: Font sizes, weights, line heights, line lengths
- BUTTON/CTA USABILITY: Visual clarity, purpose communication, affordances
- LEARNABILITY: Icon intuitiveness, label clarity, pattern familiarity

For each category, provide 0-3 critiques in Sadler's format.
If no issues found, explicitly state "No issues found" (do not
invent problems to seem thorough).
```

---

## 9. Persona-Based Prompting

**Key Research Finding**: Persona prompts significantly enhance subjective tasks. Multi-persona interaction and dynamic persona switching are the most advanced patterns. The NeurIPS 2025 PersonaLLM workshop validated these approaches.

### Design Review Panel (Multi-Persona)

```
DESIGN REVIEW PANEL TEMPLATE:

Evaluate this design from three expert perspectives:

=== VISUAL DESIGNER (Aesthetic Focus) ===
"As a visual designer with 15 years of experience in digital
product design, I evaluate:
- Color palette sophistication and brand coherence
- Typography pairing and hierarchy effectiveness
- Whitespace usage and visual breathing room
- Overall aesthetic impression and trend awareness
My assessment: ..."

=== UX ENGINEER (Technical Focus) ===
"As a UX engineer specializing in accessible, performant
front-end development, I evaluate:
- Semantic HTML structure and ARIA implementation
- CSS architecture and maintainability
- Performance implications of the design choices
- Cross-browser and cross-device compatibility
My assessment: ..."

=== END USER ADVOCATE (Usability Focus) ===
"As a UX researcher who has conducted 500+ usability tests,
I evaluate:
- First-time user comprehension (can they figure it out?)
- Task completion efficiency (can they do it quickly?)
- Error prevention and recovery (what goes wrong?)
- Emotional response and satisfaction (how does it feel?)
My assessment: ..."

=== SYNTHESIS ===
Where do all three experts agree?
Where do they disagree and why?
What is the prioritized list of improvements?
```

### Dynamic Persona Switching for Design Phases

```
PHASE-APPROPRIATE PERSONAS:

REQUIREMENTS PHASE -> Product Manager Persona:
"As a product manager, I need to understand: What problem does
this solve? Who are the users? What does success look like?"

WIREFRAME PHASE -> Information Architect Persona:
"As an information architect, I focus on: content hierarchy,
navigation patterns, user flows, and information scent."

VISUAL DESIGN PHASE -> Art Director Persona:
"As an art director, I focus on: brand expression, visual
consistency, emotional impact, and design system coherence."

IMPLEMENTATION PHASE -> Senior Frontend Developer Persona:
"As a senior frontend developer, I focus on: code quality,
performance, accessibility, maintainability, and DX."

REVIEW PHASE -> QA/Accessibility Auditor Persona:
"As an accessibility auditor, I systematically verify:
WCAG 2.1 AA compliance, keyboard navigation, screen reader
compatibility, and inclusive design patterns."
```

### Specialized Expert Personas for Web Design

```
CSS ARCHITECTURE EXPERT:
"You are a CSS architect who has maintained design systems at
scale (1000+ components, 50+ developers). You think in terms of:
- Naming conventions (BEM, utility-first, or hybrid)
- Specificity management and cascade control
- Custom property architecture for theming
- Component composition patterns
- Performance-aware CSS strategies
Evaluate and improve the CSS in this design."

RESPONSIVE DESIGN SPECIALIST:
"You are a responsive design specialist who has shipped products
used on 200+ device types. You think in terms of:
- Content-driven breakpoints (not device-driven)
- Fluid typography and spacing scales
- Component-level responsive behavior
- Touch vs pointer interaction differences
- Container queries for component independence
Evaluate and improve the responsive behavior of this design."

MOTION DESIGN EXPERT:
"You are a motion designer who creates purposeful animations.
You follow these principles:
- Animation should communicate, not decorate
- Respect prefers-reduced-motion
- Timing follows material metaphors (ease-out for entrances,
  ease-in for exits)
- Duration: micro-interactions 100-200ms, transitions 200-500ms
- Stagger related elements for visual connection
Add meaningful animation to this design."
```

---

## 10. Few-Shot Learning from Stored Examples

**Key Research Finding**: 2-3 high-quality examples are optimal. Beyond that, diminishing returns. Retrieval-augmented example selection (finding the most relevant example for the current task) outperforms random example selection.

### Design Example Storage Schema

```
EXAMPLE STORAGE FORMAT:

{
  "id": "example_001",
  "category": "navigation",
  "subcategory": "responsive_navbar",
  "complexity": "medium",
  "tags": ["mobile-first", "hamburger", "sticky", "accessible"],
  "description": "Responsive navigation bar with logo, links,
    hamburger menu, and sticky scroll behavior",
  "requirements": "Brand: TechFlow. Links: Home, Features,
    Pricing, Contact. Dark theme. Sticky on scroll.",
  "solution_html": "...",
  "solution_css": "...",
  "quality_scores": {
    "visual": 8,
    "technical": 9,
    "accessibility": 9,
    "responsive": 8
  },
  "design_decisions": [
    "Used CSS Grid for main layout, Flexbox for nav items",
    "Hamburger uses checkbox hack for CSS-only toggle",
    "Sticky uses position:sticky with scroll-margin-top"
  ],
  "lessons_learned": [
    "Always set aria-expanded on hamburger toggles",
    "Use dvh units for mobile full-height menus"
  ]
}
```

### Few-Shot Prompt with Retrieved Examples

```
FEW-SHOT DESIGN TEMPLATE:

Here are examples of high-quality designs for similar components:

=== EXAMPLE 1 (Most relevant) ===
Requirements: [retrieved example requirements]
Solution: [retrieved example code]
Key decisions: [retrieved design decisions]

=== EXAMPLE 2 (Related pattern) ===
Requirements: [retrieved example requirements]
Solution: [retrieved example code]
Key decisions: [retrieved design decisions]

=== YOUR TASK ===
Requirements: [current user request]

Create a design that:
1. Matches or exceeds the quality level shown in the examples
2. Follows the same structural patterns where applicable
3. Adapts the patterns to fit YOUR specific requirements
4. Applies the lessons learned noted in the examples
```

### Progressive Example Library Building

```
AFTER EACH DESIGN TASK:

1. EVALUATE: Score the design on visual/technical/accessibility/responsive
2. THRESHOLD CHECK: If all scores >= 7, add to example library
3. EXTRACT LESSONS: What worked well? What was tricky?
4. CATEGORIZE: Tag with component type, complexity, design patterns used
5. STORE: Add to the example library for future retrieval

RETRIEVAL STRATEGY:
When a new design task arrives:
1. Parse the task into: component_type, complexity, constraints
2. Search example library for matching category + tags
3. Rank by relevance (category match > tag overlap > quality score)
4. Select top 2 examples as few-shot context
5. If no matching examples exist, use closest available + note the gap
```

---

## 11. Synthesis: Web Design Agent Self-Improvement System

Combining all 10 techniques into a unified self-improvement architecture for a web design agent.

### The Complete Self-Improving Design Agent Loop

```
UNIFIED SELF-IMPROVEMENT ARCHITECTURE:

=== PHASE 1: INTAKE (Persona + Few-Shot) ===
- Activate Product Manager persona for requirements clarification
- Retrieve 2 most relevant examples from stored library
- Parse requirements into structured format

=== PHASE 2: EXPLORATION (Tree of Thoughts) ===
- Generate 3 design approaches (card-based, list-based, etc.)
- Evaluate each against requirements
- Select best approach or synthesize from multiple

=== PHASE 3: GENERATION (Prompt Chaining) ===
- Chain 1: Semantic HTML structure
- Chain 2: CSS visual design (activate Art Director persona)
- Chain 3: Interaction layer
- Chain 4: Responsive adaptation
Each chain's output feeds the next.

=== PHASE 4: CRITIQUE (Constitutional AI + Self-Refine) ===
- Run design constitution check (accessibility, hierarchy, performance)
- Apply Self-Refine loop (generate -> critique -> revise, max 3 iterations)
- Use Multi-Persona review panel for comprehensive assessment
- Apply UICrit Sadler's format for specific issues

=== PHASE 5: REFLECTION (Reflexion) ===
- Score final design against evaluation rubric
- Generate verbal reflection on what worked and what did not
- Extract generalizable lessons
- Store in memory for future tasks

=== PHASE 6: META-LEARNING (Meta-Prompting + Self-Instruct) ===
- If design scored >= 7 on all axes: add to example library
- Use contrastive analysis: compare this output to previous versions
- Update internal prompt templates based on what produced better results
- Generate new training tasks from successful patterns (Self-Instruct)

=== PHASE 7: HONEST ASSESSMENT (Self-Calibration) ===
- Calibrate confidence on each design decision
- Flag low-confidence decisions for user review
- Maintain honesty about limitations and trade-offs
```

### Concrete Implementation Prompt

```
WEB DESIGN AGENT SYSTEM PROMPT:

You are a senior web designer and frontend developer with expertise
in modern CSS, semantic HTML, accessibility, and responsive design.

CORE BEHAVIOR:
1. Before designing, clarify requirements (Product Manager mode)
2. Explore 2-3 approaches before committing (Tree of Thoughts)
3. Build in phases: structure -> style -> interaction -> responsive
4. After generating, self-critique against your design constitution
5. Revise based on critique (max 3 refinement cycles)
6. Honestly assess your confidence in the final result
7. Extract lessons for future improvement

DESIGN CONSTITUTION:
[Insert full constitution from Section 1]

QUALITY STANDARDS:
- All designs must pass WCAG AA accessibility
- All designs must be responsive (320px to 1920px)
- All HTML must be semantic and valid
- All CSS must use custom properties for theming
- All interactive elements must have visible focus states

SELF-IMPROVEMENT PROTOCOL:
After each task, reflect:
1. What design decisions am I most/least confident about?
2. What would I do differently next time?
3. What new pattern or technique did I learn?
4. What should I add to my example library?

HONESTY REQUIREMENTS:
- Never claim a design is "excellent" without evidence
- Always flag areas of uncertainty
- Admit when a requirement is beyond your capability
- Prefer "I'm not sure, let me verify" over fabrication
```

### Evaluation Rubric (WebDevJudge-Inspired)

```
WEB DESIGN EVALUATION RUBRIC TREE:

ROOT: Overall Design Quality

  BRANCH 1: Intention (Does it meet requirements?)
    LEAF 1.1: All stated features are present [pass/fail]
    LEAF 1.2: Content matches specifications [pass/fail]
    LEAF 1.3: No unrequested features added [pass/fail]
    LEAF 1.4: Edge cases handled [pass/fail]

  BRANCH 2: Static Quality (Does it look right?)
    LEAF 2.1: Visual consistency maintained [pass/fail]
    LEAF 2.2: Color contrast meets WCAG AA [pass/fail]
    LEAF 2.3: Typography hierarchy is clear [pass/fail]
    LEAF 2.4: Spacing is consistent [pass/fail]
    LEAF 2.5: Layout works at all breakpoints [pass/fail]
    LEAF 2.6: Images/icons are appropriate [pass/fail]

  BRANCH 3: Dynamic Behavior (Does it work right?)
    LEAF 3.1: Interactive elements have feedback [pass/fail]
    LEAF 3.2: Transitions are smooth and purposeful [pass/fail]
    LEAF 3.3: Keyboard navigation works [pass/fail]
    LEAF 3.4: Screen reader experience is logical [pass/fail]
    LEAF 3.5: Loading/error states exist [pass/fail]
    LEAF 3.6: Form validation is helpful [pass/fail]

SCORING:
- Pass rate per branch (e.g., Static: 5/6 = 83%)
- Overall pass rate (e.g., 14/16 = 87.5%)
- Any LEAF 1.x failure = Critical (must fix)
- Any LEAF 2.x or 3.x failure = Important (should fix)
```

---

## Sources

### Constitutional AI
- [Constitutional AI: Harmlessness from AI Feedback (Anthropic, 2022)](https://arxiv.org/abs/2212.08073)
- [C3AI: Crafting and Evaluating Constitutions - ACM Web Conference 2025](https://dl.acm.org/doi/10.1145/3696410.3714705)
- [Collective Constitutional AI (Anthropic)](https://www.anthropic.com/research/collective-constitutional-ai-aligning-a-language-model-with-public-input)
- [Constitutional AI Principle-Based Alignment (Brenndoerfer)](https://mbrenndoerfer.com/writing/constitutional-ai-principle-based-alignment-through-self-critique)

### Self-Instruct
- [Self-Instruct: Aligning Language Models with Self-Generated Instructions](https://arxiv.org/abs/2212.10560)
- [Self-Instruct Framework Explained (Towards Data Science)](https://towardsdatascience.com/self-instruct-framework-explained-16bce90f4683/)
- [Synthetic Dataset Generation: Self-Instruct (Hugging Face)](https://huggingface.co/blog/davanstrien/self-instruct)
- [CoT-Self-Instruct (2025)](https://arxiv.org/pdf/2507.23751)

### Chain of Thought Variations
- [Critic-CoT: Boosting Reasoning via Chain-of-Thought Critic (ACL 2025)](https://aclanthology.org/2025.findings-acl.89/)
- [Self-Reflection Enhances LLMs - Nature (2025)](https://www.nature.com/articles/s44387-025-00045-3)
- [Self-Criticism Prompting Techniques (Learn Prompting)](https://learnprompting.org/docs/advanced/self_criticism/introduction)
- [Reflexion Framework (Prompt Engineering Guide)](https://www.promptingguide.ai/techniques/reflexion)
- [Multi-Agent Reflexion (MAR)](https://arxiv.org/html/2512.20845)
- [Self-Harmonized Chain-of-Thought (ECHO)](https://learnprompting.org/docs/new_techniques/self_harmonized_chain_of_thought)

### Tree of Thoughts
- [Tree of Thoughts (Prompt Engineering Guide)](https://www.promptingguide.ai/techniques/tot)
- [What is Tree of Thoughts Prompting (IBM)](https://www.ibm.com/think/topics/tree-of-thoughts)
- [Tree of Thoughts Prompting (Cameron Wolfe)](https://cameronrwolfe.substack.com/p/tree-of-thoughts-prompting)

### Graph of Thoughts
- [Graph of Thoughts: Solving Elaborate Problems with LLMs](https://arxiv.org/abs/2308.09687)
- [Demystifying Chains, Trees, and Graphs of Thoughts (ETH Zurich)](https://htor.inf.ethz.ch/publications/img/besta-topologies.pdf)
- [Graph of Thoughts GitHub (ETH SPCL)](https://github.com/spcl/graph-of-thoughts)

### Prompt Chaining
- [Prompt Chaining (Prompt Engineering Guide)](https://www.promptingguide.ai/techniques/prompt_chaining)
- [Prompt Chaining for AI Engineers (Maxim)](https://www.getmaxim.ai/articles/prompt-chaining-for-ai-engineers-a-practical-guide-to-improving-llm-output-quality/)
- [Prompt Chaining - Agentic Design Patterns](https://agentic-design.ai/patterns/prompt-chaining)

### Meta-Prompting
- [Complete Guide to Meta Prompting (PromptHub)](https://www.prompthub.us/blog/a-complete-guide-to-meta-prompting)
- [Enhance Your Prompts with Meta Prompting (OpenAI Cookbook)](https://cookbook.openai.com/examples/enhance_your_prompts_with_meta_prompting)
- [Meta Prompting (Prompt Engineering Guide)](https://www.promptingguide.ai/techniques/meta-prompting)
- [Meta-Prompting: LLMs Crafting Their Own Prompts (IntuitionLabs)](https://intuitionlabs.ai/articles/meta-prompting-llm-self-optimization)
- [DSPy: The Framework for Programming Language Models](https://dspy.ai/)
- [Prompt Engineering Techniques: Top 6 for 2026 (K2View)](https://www.k2view.com/blog/prompt-engineering-techniques/)

### Honest Self-Assessment
- [LLM Self-Evaluation (Learn Prompting)](https://learnprompting.org/docs/reliability/lm_self_eval)
- [LLM-as-a-Judge Complete Guide (Evidently AI)](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [Survey on the Honesty of LLMs (2025 TMLR)](https://github.com/SihengLi99/LLM-Honesty-Survey)

### Persona-Based Prompting
- [Role Prompting Guide (Learn Prompting)](https://learnprompting.org/docs/advanced/zero_shot/role_prompting)
- [Pattern Language for Persona-based Interactions (Vanderbilt)](https://www.dre.vanderbilt.edu/~schmidt/PDF/Persona-Pattern-Language.pdf)
- [PersonaLLM Workshop - NeurIPS 2025](https://personallmworkshop.github.io/)
- [Operational Protocol Method for LLM Specialization (LLRX 2025)](https://www.llrx.com/2025/09/the-operational-protocol-method-systematic-llm-specialization-through-collaborative-persona-engineering-and-agent-coordination/)

### Few-Shot Learning
- [Few-Shot Prompting (Prompt Engineering Guide)](https://www.promptingguide.ai/techniques/fewshot)
- [Few-Shot Prompting Guide (PromptHub)](https://www.prompthub.us/blog/the-few-shot-prompting-guide)
- [What is Few Shot Prompting (IBM)](https://www.ibm.com/think/topics/few-shot-prompting)

### Web Design Evaluation
- [WebDevJudge: Evaluating LLMs as Critiques for Web Development Quality (2025)](https://arxiv.org/html/2510.18560v1)
- [UICrit: Enhancing Automated Design Evaluation](https://arxiv.org/html/2407.08850v2)
- [LLM UI Design Rankings 2025 (SmartScope)](https://smartscope.blog/en/ai-development/llm-ui-design-ranking-2025/)
