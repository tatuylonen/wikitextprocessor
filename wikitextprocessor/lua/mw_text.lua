-- Simplified implementation of mw.text for running WikiMedia Scribunto code
-- under Python
--
-- Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

local mw_text = {
   -- decode (set from Python)
   -- encode (set from Python)
   -- gsplit (see below)
   -- jsonDecode (see below, calls Python)
   -- jsonEncode (see below, calls Python)
   -- killMarkers (see below)
   -- listToText  (see below)
   -- nowiki  (see below)
   -- split (see below)
   -- tag (see below)
   -- trim (see below)
   -- truncate (see below)
   -- unstripNoWiki (see below)
   -- unstrip (see below)
   JSON_PRESERVE_KEYS = 1,
   JSON_TRY_FIXING = 2  -- we ignore this flag
}

function mw_text.gsplit(text, pattern, plain)
   local result = mw_text.split(text, pattern, plain)
   local i = 0
   local n = table.getn(result)
   return function()
         i = i + 1
         if i <= n then return result[i] end
   end
end

function mw_text.jsonDecode(value, flags)
   flags = flags or 0
   return mw_jsondecode_python(value, flags)
end

function mw_text.jsonEncode(value, flags)
   flags = flags or 0
   return mw_jsonencode_python(value, flags)
end

function mw_text.decode(value, decodeNamedEntities)
   return mw_decode_python(value, decodeNamedEntities)
end

function mw_text.encode(value, charset)
   if charset == nil then charset="\"<>& " end
   return mw_encode_python(value, charset)
end

function mw_text.killMarkers(s)
   -- we have our magic characters, but I don't think they are visible to Lua
   -- (except perhaps the nowiki magic)
   print("mw.text.killMarkers called")
   return s
end

function mw_text.tag(name, attrs, content)
   if type(name) == "table" then
      attrs = name.attrs
      content = name.content
      name = name.name
   end
   local t = mw.html.create(name)
   if attrs ~= nil then
      for k, v in pairs(attrs) do
         t:attr(k, v)
      end
   end
   if content ~= nil and content ~= false then
      t:wikitext(content)
   end
   return tostring(t)
end

function mw_text.trim(s, charset)
   charset = charset or "\r\n\t\f "
   local ret = mw.ustring.gsub(s, "^[" .. charset .. "]*(.-)[" ..
                                  charset .. "]*$", "%1")
   return ret
end

function mw_text.truncate(text, length, ellipsis, adjustLength)
   if not length or length == 0 then
      return text
   end
   if ellipsis == nil then
      ellipsis = "…"
   end
   if #text <= length then
      return text
   end
   if length >= 0 then
      if adjustLength and ellipsis then
         length = length - #ellipsis
      end
      text = mw.ustring.sub(text, 1, length)
      if ellipsis then
         text = text .. ellipsis
      end
   else
      if adjustLength and ellipsis then
         length = length + #ellipsis
      end
      text = mw.ustring.sub(text, #text + length + 1)
      if ellipsis then
         text = ellipsis .. text
      end
   end
   return text
end

function mw_text.unstripNoWiki(s)
   print("mw.text.unstripNoWiki called")
   -- We don't currently do anything here
   return s
end

function mw_text.unstrip(s)
   return mw.text.killMarkers(mw.text.untripNoWiki(s))
end

function mw_text.listToText(list, separator, conjunction)
   -- XXX default separators should be language-dependent
   if separator == nil then separator = "," end
   if conjunction == nil then conjunction = "and" end
   if #list == 0 then return "" end
   if #list == 1 then return list[1] end
   if #list == 2 then return list[1] .. " " .. conjunction .. " " .. list[2] end
   local lst = {}
   for i = 1, #list - 2 do
      table.insert(lst, list[i])
      table.insert(lst, separator)
      table.insert(lst, " ")
   end
   table.insert(lst, list[#list - 1])
   table.insert(lst, " ")
   table.insert(lst, conjunction)
   table.insert(lst, " ")
   table.insert(lst, list[#list])
   return table.concat(lst, "")
end

function mw_text.split(text, pattern, plain)
   local result = {}
   local start = 1
   local length = mw.ustring.len(text)
   while start <= length do
      local ofs, last = mw.ustring.find(text, pattern, start, plain)
      if ofs == nil then
         break
      elseif ofs > last then
         -- empty match
         table.insert(result, mw.ustring.sub(text, start, ofs))
         start = ofs + 1
         if start == length then
            table.insert(result, mw.ustring.sub(text, start))
         end
         if start >= length then
            return result
         end
      elseif ofs == start then
         table.insert(result, "")
         start = last + 1
      else
         table.insert(result, mw.ustring.sub(text, start, ofs - 1))
         start = last + 1
      end
   end
   table.insert(result, mw.ustring.sub(text, start))
   return result
end

function mw_text.nowiki(s)
   s = s:gsub("&", "&amp;")
   s = s:gsub('"', "&quot;")
   s = s:gsub("'", "&apos;")
   s = s:gsub("<", "&lt;")
   s = s:gsub(">", "&gt;")
   s = s:gsub("=", "&#61;")
   s = s:gsub("%[", "&lsqb;")
   s = s:gsub("%]", "&rsqb;")
   s = s:gsub("{", "&lbrace;")
   s = s:gsub("}", "&rbrace;")
   s = s:gsub("|", "&vert;")
   s = s:gsub("^#", "&num;")
   s = s:gsub("\n#", "\n&num;")
   s = s:gsub("^:", "&colon;")
   s = s:gsub("\n:", "\n&colon;")
   s = s:gsub("^;", "&semi;")
   s = s:gsub("\n;", "\n&semi;")
   s = s:gsub("^ ", "&nbsp;")
   s = s:gsub("\n ", "\n&nbsp;")
   s = s:gsub("^\t", "&Tab;")
   s = s:gsub("\n\t", "\n&Tab;")
   s = s:gsub("\n\n", "\n&NewLine;")
   s = s:gsub("^%-%-%-%-", "&minus;---")
   s = s:gsub("\n%-%-%-%-", "\n&minus;---")
   s = s:gsub("^__", "&#95;_")
   s = s:gsub("\n__", "\n&#95;_")
   s = s:gsub("://", "&colon;//")
   s = s:gsub("ISBN ", "ISBN&nbsp;")
   s = s:gsub("ISBN\t", "ISBN&Tab;")
   s = s:gsub("ISBN\n", "ISBN&NewLine;")
   s = s:gsub("RFC ", "ISBN&nbsp;")
   s = s:gsub("RFC\t", "ISBN&Tab;")
   s = s:gsub("RFC\n", "ISBN&NewLine;")
   s = s:gsub("PMID ", "ISBN&nbsp;")
   s = s:gsub("PMID\t", "ISBN&Tab;")
   s = s:gsub("PMID\n", "ISBN&NewLine;")
   return s
end

return mw_text
