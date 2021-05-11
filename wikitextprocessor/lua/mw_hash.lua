-- Simplified implementation of mw.hash for running WikiMedia Scribunto code
-- under Python
--
-- Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

local mw_hash = {
}

function mw_hash.hashValue(algo, value)
  print("MW_HASH_HASHVALUE")
end

function mw_hash.listAlgorithms()
  print("MW_HASH_LISTALGORITHMS")
  return {}
end

return mw_hash
