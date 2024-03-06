-- Simplified sub implementation of mw.ext for running WikiMedia Scribunto
-- code under Python
--
-- Copyright (c) 2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- https://www.mediawiki.org/wiki/Extension:Scribunto/Lua_reference_manual#mw.ext.data
-- https://www.mediawiki.org/wiki/Extension:JsonConfig/Tabular
-- https://www.mediawiki.org/wiki/Help:Tabular_Data
local mw_ext = { data = {} }

-- https://github.com/wikimedia/mediawiki-extensions-JsonConfig/blob/master/includes/JCLuaLibrary.php
function mw_ext.data.get(title, lang_code)
    return {
        license = "CC0-1.0",
        schema = { fields = {} },
        data = {},
    }
end

return mw_ext
