from pygments import lex
from pygments.lexers import CLexer
from pygments.token import Comment, Keyword, Literal, Name, Operator, Punctuation, Text


class Highlight:
    def __init__(self, logger, src_file):
        self.logger = logger

        with open(src_file) as fp:
            src = fp.read()

        self.tokens = lex(src, CLexer())

        # Current token line number.
        self.cur_line_numb = 1
        # Current token start offset within current line.
        self.cur_start_offset = 0

        # List of entities (each represented as kind, line number, start and end offsets) to be highligted
        self.highlights = list()

    # Go to the next line, reset current token start offset and skip normal location update when meet new line symbol.
    def go_to_next_line(self, c='\n'):
        if c == '\n':
            self.cur_line_numb += 1
            self.cur_start_offset = 0
            return True
        else:
            return False

    def highlight(self):
        for token in self.tokens:
            token_type, token_text = tuple(token)
            token_len = len(token_text)

            # Handle token types that do not need special processing.
            if token_type in (
                Comment.PreprocFile,
                Comment.Single,
                Keyword,
                Keyword.Type,
                Keyword.Reserved,
                Literal.Number.Hex,
                Literal.Number.Integer,
                Literal.Number.Oct,
                Literal.String,
                Literal.String.Char,
                Literal.String.Escape,
                Name,
                Name.Builtin,
                Name.Label,
                Operator
            ):
                self.highlights.append([
                    ''.join([k[0] for k in tuple(token_type)]),
                    self.cur_line_numb,
                    self.cur_start_offset,
                    self.cur_start_offset + token_len
                ])
            # Trailing "\n" may be included into single line comment.
            elif token_type is Comment:
                if token_text[-1] == '\n':
                    self.highlights.append([
                        'C',
                        self.cur_line_numb,
                        self.cur_start_offset,
                        self.cur_start_offset + token_len - 1
                    ])
                    self.go_to_next_line()
                    continue
                else:
                    self.highlights.append([
                        'C',
                        self.cur_line_numb,
                        self.cur_start_offset,
                        self.cur_start_offset + token_len
                    ])
            elif token_type is Comment.Multiline:
                comment_start_offset = self.cur_start_offset

                for c in token_text:
                    # Remember current values as core.highlight.Highlight#go_to_next_line can modify them.
                    cur_line_numb = self.cur_line_numb
                    cur_start_offset = self.cur_start_offset
                    if self.go_to_next_line(c):
                        # There may be empty lines containing just "\n" within multiline comments.
                        if comment_start_offset < cur_start_offset:
                            self.highlights.append([
                                'CM',
                                cur_line_numb,
                                comment_start_offset,
                                cur_start_offset
                            ])
                        comment_start_offset = self.cur_start_offset
                    else:
                        self.cur_start_offset += 1

                # Add last multiline comment line.
                self.highlights.append([
                    'CM',
                    self.cur_line_numb,
                    comment_start_offset,
                    self.cur_start_offset
                ])
                continue
            elif token_type is Comment.Preproc:
                # "\n" at the end of preprocessor directives is treated as Comment.Preproc rather than Text.
                if self.go_to_next_line(token_text):
                    continue

                # Trailing "\n" could be included into Comment.Preproc like for Comment.
                if token_text[-1] == '\n':
                    self.highlights.append([
                        'CP',
                        self.cur_line_numb,
                        self.cur_start_offset,
                        self.cur_start_offset + token_len - 1
                    ])
                    self.go_to_next_line()
                    continue
                else:
                    self.highlights.append([
                        'CP',
                        self.cur_line_numb,
                        self.cur_start_offset,
                        self.cur_start_offset + token_len
                    ])
            # Highlighting for functions is performed together with building cross references.
            elif token_type is Name.Function:
                pass
            # There is no special highlighting for punctuation.
            elif token_type is Punctuation:
                pass
            # There is no special highlighting for text.
            elif token_type is Text:
                # Sometimes "\n" is preceded by some text or concatenated with text from following lines.
                if len(token_text) == 1:
                    if self.go_to_next_line(token_text):
                        continue
                elif token_text[-1] == '\n':
                    self.go_to_next_line()
                    continue
                elif self.go_to_next_line(token_text[0]):
                    # Skip the rest of text token length.
                    self.cur_start_offset += token_len - 1
                    continue
            else:
                self.logger.warning("Does not support token \"{0}\" of type \"{1}\"".format(token_text, token_type))

            # Update current token start offset according to current token length.
            self.cur_start_offset += token_len

    # In core.highlight.Highlight#highlight we assume that highlighted entity locations do not overlap. But there may
    # be other more important sources for highlighting, e.g. for cross referencing, so, we may need to remove overlaps.
    def extra_highlight(self, extra_highlights):
        # Remove previous less important highlights that are overlapped with extra ones.
        # Store highlights to be removed and remove them later at once rather than create new list of highlights each
        # time when some highlights should be removed. This should work much faster since we expect that there are very
        # many highlights and just few highlights should be removed
        highlights_to_be_removed = list()
        for extra_highlight in extra_highlights:
            extra_highlight_line_numb, extra_highlight_start_offset, extra_highlight_end_offset = extra_highlight[1:]

            for highlight in self.highlights:
                highlight_line_numb, highlight_start_offset, highlight_end_offset = highlight[1:]
                if highlight_line_numb == extra_highlight_line_numb:
                    if highlight_start_offset <= extra_highlight_end_offset \
                            and highlight_end_offset >= extra_highlight_start_offset:
                        highlights_to_be_removed.append(highlight)

        if highlights_to_be_removed:
            self.highlights = [highlight for highlight in self.highlights if highlight not in highlights_to_be_removed]

        # Add extra highlights.
        for extra_highlight in extra_highlights:
            self.highlights.append(extra_highlight)


# TODO: remove!!!
highlight = Highlight(None, '/home/novikov/work/klever-data/build bases/linux-3.14.79/Storage/home/novikov/work/klever-data/linux-stable/drivers/ata/pata_arasan_cf.c')
highlight.highlight()
for h in highlight.highlights:
    print(h)