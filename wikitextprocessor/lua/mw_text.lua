-- Simplified implementation of mw.text for running WikiMedia Scribunto code
-- under Python
--
-- Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- Use the original WikiMedia Scribunto code for some things
scribunto_mwtext = require("mw.text")

local mw_text = {
   -- decode (set from Python)
   -- encode (set from Python)
   -- jsonDecode
   -- jsonEncode
   -- killMarkers
   -- listToText  (see below)
   -- nowiki  (see below)
   split = scribunto_mwtext.split,
   gsplit = scribunto_mwtext.gsplit,
   -- tag
   trim = scribunto_mwtext.trim
   -- truncate
   -- unstripNoWiki
   -- unstrip (see below)
}

function mw_text.jsonDecode(s, flags)
   print("XXX mw_text.jsonDecode")
   return nil
end

function mw_text.jsonEncode(value, flags)
   print("XXX mw_text.jsonEncode")
   return nil
end

function mw_text.killMarkers(s)
   -- we have our magic characters, but I don't think they are visible to Lua
   -- (except perhaps the nowiki magic)
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
   print("XXX mw_text.unstrupNoWiki")
   return nil
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
