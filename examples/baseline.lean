import Lean
import Std


theorem target (α : Type) (xs ys : List α) : (xs ++ ys).length = xs.length + ys.length := by
  simp
