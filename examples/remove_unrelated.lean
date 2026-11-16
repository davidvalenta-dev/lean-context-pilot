import Lean
import Std

attribute [-simp] Nat.add_zero

theorem target (α : Type) (xs ys : List α) : (xs ++ ys).length = xs.length + ys.length := by
  simp
