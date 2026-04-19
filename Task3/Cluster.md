# Framework: Regional Clustering Algorithm (Northeast USA)

## 1. Problem Definition & Scope
**Algorithm Type:** Spatial Clustering / Combinatorial Optimization
**Objective:** Group smaller geographic units into larger operational regions based on specific logistics and spatial criteria.
**Scale (Parameters):** * **Base Units:**  Counties
* **Target Output:** Aggregation into $x = 50$ Regions

## 2. Design Criteria (Cluster Characteristics)
The algorithm must balance conflicting spatial and operational characteristics through an appropriate weighting scheme. These criteria translate into either hard constraints or components of the objective function.

* **Spatial Contiguity:** Counties within a region must form a connected geographic area without fragmentation. *(Treated as a Hard Constraint).*
* **Balanced Freight Demand:** Regions should have relatively balanced freight demand (e.g., measured in tonnage) to avoid a highly uneven workload across regions.
* **Alignment with Logistics Infrastructure:** Cluster boundaries should naturally follow or respect major transportation infrastructure (e.g., interstate corridors, rail networks) to reflect real freight movement patterns.
* **Compactness:** Regions should be spatially compact to limit excessive travel distances and maintain operational efficiency. *(Also features a "diameter cap" as a Hard Constraint).*

## 3. Mathematical Formulation
To balance the conflicting criteria simultaneously, the algorithm relies on a weighted cost/objective function $J$.

**Global Objective Function ($J$):**
$$J = w_{align} \cdot (\text{alignment metric}) + w_{compactness} \cdot (\text{compactness metric}) + w_{balance} \cdot (\text{tonnage balance})$$

**Delta Evaluation ($\Delta J$):** When proposing a change to the clusters, the algorithm calculates the change in the cost function:
$$\Delta J = \Delta_{alignment} + \Delta_{compactness} + \Delta_{demand\_balance}$$

## 4. Algorithmic Approach: "Simulated Annealing" Inspired Clustering
The implementation follows a 4-step iterative process based on the Simulated Annealing metaheuristic.

### Step 1: Build Adjacency Graph & Warm Start (Initialization)
* **Action:** Create an adjacency graph of all counties.
* **Initialization:** Use a region-growing seed approach to create an initial $k$-region assignment (where $k=50$).
* **Purpose:** Ensures initial spatial contiguity to give the algorithm a valid starting state.

### Step 2: Propose Border Move (Neighborhood Structure)
* **Action:** Randomly select a county located on the border between two regions.
* **Proposal:** Propose reassigning this selected county to its neighboring region.

### Step 3: Check Constraints and Evaluate $\Delta J$
* **Hard Constraints Check:** Automatically **reject** the proposed move if it:
    1.  Breaks spatial contiguity (leaves a county or group of counties stranded).
    2.  Exceeds the regional diameter cap (makes the region too wide/long).
* **Evaluation:** If constraints are satisfied, compute $\Delta J$ using the formula provided in Section 3.

### Step 4: Accept / Reject & Cool
* **Acceptance Criteria:**
    * If $\Delta J < 0$ (the move improves the clusters), **Accept** the move.
    * If $\Delta J \ge 0$ (the move worsens the clusters), **Accept with probability:** $e^{\frac{-\Delta J}{T}}$
* **Cooling Schedule:** Decrease the "Temperature" parameter ($T$).
* **Termination:** Repeat Steps 2–4 until convergence criteria are met (e.g., $T$ reaches near zero, or no improvements are found over a set number of iterations).

---
## 5. Notes for LLM Implementation
*Data Requirements:* To implement this, the code will require an adjacency matrix/list for all the counties in NE, geographic centroids/shapes for compactness calculations, freight tonnage data per county, and infrastructure overlap data.
*Graph Theory Application:* Step 3's contiguity check will likely require a fast graph traversal algorithm (like Depth-First Search or Breadth-First Search) on the subgraph of the losing region to ensure it remains connected after a border county is removed.