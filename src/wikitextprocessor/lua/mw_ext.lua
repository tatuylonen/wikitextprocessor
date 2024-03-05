-- Simplified sub implementation of mw.ext for running WikiMedia Scribunto
-- code under Python
--
-- Copyright (c) 2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- https://doc.wikimedia.org/Wikibase/master/php/docs_topics_lua.html
local mw_ext= { data = {}
}

function mw_ext.data.get(title, lang_code)
    return { license = "CC0-1.0",
             schema = { fields = {} },
             data = {}
           }
end

return mw_ext
