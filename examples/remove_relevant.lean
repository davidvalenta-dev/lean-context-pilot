import Lean
import Std

attribute [-simp] List.length_append

theorem target (α : Type) (xs ys : List α) : (xs ++ ys).length = xs.length + ys.length := by
  simp
