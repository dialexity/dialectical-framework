Your task is to design and implement a reporting feature that:

- Automatically generates visual and textual reports, inspired by the examples provided in the attached PDF (use them as references, not fixed templates).
- Provides a smooth, intuitive parameter selection interface, allowing users to tailor the analysis and output to their needs.

Below is an outline of possible settings to support — feel free to propose cleaner, more effective alternatives during implementation. Not all options are required in the MVP, but they illustrate the scope and flexibility we’re aiming for.

## Main Settings Window
### Section 1: Core Analysis Settings
**Concept Source**
- Text Analysis (from text or document)  
- Direct Entry

**Number of Components** [Dropdown: 1, 2, 3, 4]

**Component Definition** [Dropdown]
- General Concepts (default)
- Action Plan/Steps  
- Problem/Solution
- Custom Label [text field appears when selected]

### Section 2: Component Length Settings

**Word Limits:**
- Brief (1-2 words)
- Standard (3-4 words) [default]
- Detailed (5+ words)

**Single Thesis Mode:** (checkbox - only visible when Number of Components = 1)

When checked, reveals:
- Main Thesis: [slider 1-7 words, default 5]
- Antithesis: [slider 1-5 words, default 3]  
- Components (T+, T-, A+, A-): [slider 1-3 words, default 2]

### Section 3: Analysis Depth

**Sequence Analysis:** (only visible when Number of Components = 2, 3, or 4)
- Generate sequence probabilities
- Compare alternative sequences

**Sequence Evaluation Priority:** (Dropdown - only visible when sequence analysis enabled)
- Most Realistic (what typically happens)
- Most Desirable (optimal outcomes)  
- Most Feasible (achievable implementation)
- Balanced Assessment (considers all factors) [default]

### Section 4: Output Options

**Include in Analysis:**
- Component actualization (how concepts manifest in reality)
- Step-by-step interpretation  
- Implementation timeline
- Dialectical complementary solutions (problem-solving focus)

## Advanced Options Modal/Panel

*Triggered by: "Advanced Options" button in main settings*

### Section 1: Synthesis Analysis

**Generate Positive/Negative Syntheses:**
- Enable synthesis analysis for each T/A pair

**Synthesis Detail Level:**
- Basic (S+ and S- identification only)
- Standard (includes real-life examples) [default]
- Comprehensive (includes system transformation analysis)

### Section 2: Enhanced Explanations

**Additional Context:**
- Detailed antithetical domain explanations
- Transition mechanism analysis (how concepts transform into each other)
- Historical/cultural context examples
- Stakeholder responsibility mapping

### Section 3: Export & Integration

**Output Format:**
- Include technical definitions
- Generate implementation roadmap
- Create stakeholder analysis
- Export wheel visualization

**File Formats:**
- PDF Report 
- JSON Data 
- SVG Wheel

## Window Behavior Specifications

### Progressive Disclosure
- Single Component (N=1): Shows single thesis mode options, hides sequence analysis
- Multiple Components (N=2-4): Shows sequence analysis options, hides single thesis mode
- Advanced features: Collapsed by default, expandable via "Advanced Options"
### Default State
- Concept Source: Text Analysis
- Number of Components: 4
- Component Definition: General Concepts  
- Word Limits: Standard
- Sequence Analysis: Enabled with "Balanced Assessment"
- Basic Output Options: All checked except "Implementation timeline"
- Advanced Options: Collapsed
### Conditional Logic
- Synthesis analysis only appears when dialectical components are being generated
- Stakeholder mapping only appears when analyzing organizational/process systems
- Export options only become active after analysis is complete
## User Experience Notes
- Settings should persist across sessions
- "Quick Start" preset buttons for common use cases:
  - **Academic Analysis:** Detailed word limits, comprehensive explanations
  - **Business Strategy:** Feasible sequences, stakeholder mapping, implementation focus
  - **Personal Reflection:** Single thesis mode, basic synthesis analysis
  - **System Design:** All advanced options enabled