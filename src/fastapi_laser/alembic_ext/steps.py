from dataclasses import dataclass, field
import random
from typing import Any, Callable, Collection, Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def noop() -> None:
    """A noop function, i.e. a function that does nothing.

    Intended to be a callable instance attribute default value."""


@dataclass
class MigrationStep:
    pre_upgrade: Callable[[Any], None] = noop
    post_upgrade: Callable[[Any], None] = noop
    pre_downgrade: Callable[[Any], None] = noop
    post_downgrade: Callable[[Any], None] = noop
    renderer_convertors: list[Callable[[Any], None]] = field(default_factory=list)

    # TODO: implement, priority 3
    @classmethod
    def for_case__rename_table(cls) -> "MigrationStep":
        # TODO:
        #  [app code] decorate model field to mark with the old name
        #  disable deletion in autogenerated code
        #  alter table based on decorator args

        raise NotImplementedError

    # TODO: implement, priority 2
    @classmethod
    def for_case__rename_column(cls) -> "MigrationStep":
        # TODO:
        #  [app code] decorate model field to mark with the old name
        #  disable deletion in autogenerated code
        #  alter column based on decorator args

        raise NotImplementedError

    # TODO: implement, priority 4
    @classmethod
    def for_case__move_column_data(cls) -> "MigrationStep":
        raise NotImplementedError

    # case__create_column_with_enum
    # -> achieved through other means
    #   pre_upgrade: create enum type if not extant
    #   upgrade: [sa autogen] create column
    #   downgrade: [sa autogen] drop column
    #   post_downgrade: drop enum type if not used by other columns

    # case__drop_column_with_enum
    # -> achieved through other means
    #   upgrade: [sa autogen] drop column
    #   post_upgrade: drop enum type if not used by other columns
    #   pre_downgrade: create enum type if not extant
    #   downgrade: [sa autogen] create column

    # TODO: determine enum_new_members from diff with old enum using git history
    # TODO: decide whether data using new members should be deleted or modified
    @classmethod
    def for_case__add_enum_members(
        cls,
        columns_by_table: dict[str, Collection[str]],
        enum_added_to_old_member_map: dict[str, Optional[str]],
        enum_name: str,
        *new_enum_members: str,
    ) -> "MigrationStep":
        # TODO: explain in docstring using an example
        new_members = set(new_enum_members)
        old_members = new_members - set(enum_added_to_old_member_map)

        def post_upgrade():
            execute_replace_columns_enum_type(columns_by_table, enum_name, *new_members)

        def pre_downgrade():
            for table_name, column_names in columns_by_table.items():
                for column_name in column_names:
                    execute_remap_enum_members_or_delete_rows(
                        table_name,
                        column_name,
                        enum_name,
                        **enum_added_to_old_member_map,
                    )

            execute_replace_columns_enum_type(columns_by_table, enum_name, *old_members)

        return cls(post_upgrade=post_upgrade, pre_downgrade=pre_downgrade)

    @classmethod
    def for_case__remove_enum_members(
        cls,
        columns_by_table: dict[str, Collection[str]],
        enum_removed_to_new_member_map: dict[str, Optional[str]],
        enum_name: str,
        *new_enum_members: str,
    ) -> "MigrationStep":
        # TODO: explain in docstring using an example
        new_members = set(new_enum_members)
        old_members = new_members | set(enum_removed_to_new_member_map)

        def post_upgrade():
            for table_name, column_names in columns_by_table.items():
                for column_name in column_names:
                    execute_remap_enum_members_or_delete_rows(
                        table_name,
                        column_name,
                        enum_name,
                        **enum_removed_to_new_member_map,
                    )

            execute_replace_columns_enum_type(columns_by_table, enum_name, *new_members)

        def pre_downgrade():
            execute_replace_columns_enum_type(columns_by_table, enum_name, *old_members)

        return cls(post_upgrade=post_upgrade, pre_downgrade=pre_downgrade)

    # TODO: implement, priority 3
    @classmethod
    def for_case__rename_enum_members(cls) -> "MigrationStep":
        def pre_upgrade():
            raise NotImplementedError

        def post_downgrade():
            raise NotImplementedError

        return cls(pre_upgrade=pre_upgrade, post_downgrade=post_downgrade)

    @classmethod
    def for_case__create_enum(cls, enum_name, *enum_members):
        def pre_upgrade():
            sa.Enum(*enum_members, name=enum_name).create(op.get_bind())

        def post_downgrade():
            sa.Enum(name=enum_name).drop(op.get_bind())

        return cls(pre_upgrade=pre_upgrade, post_downgrade=post_downgrade)

    @classmethod
    def for_case__drop_enum(cls, enum_name, *enum_members):
        def post_upgrade():
            sa.Enum(name=enum_name).drop(op.get_bind())

        def pre_downgrade():
            sa.Enum(*enum_members, name=enum_name).create(op.get_bind())

        return cls(post_upgrade=post_upgrade, pre_downgrade=pre_downgrade)

    # TODO: implement, priority 3
    @classmethod
    def for_case__rename_enum(cls) -> "MigrationStep":
        def pre_upgrade():
            # TODO:
            #  create temp new enum type
            #  for all columns using enum:
            #    replace old enum with temp new enum
            #  drop old enum type
            #  create new enum type with old name
            #  for all columns using enum:
            #    replace temp new enum with new enum with old name

            raise NotImplementedError

        def post_downgrade():
            # TODO: the same operations swapping the old enum for the new enum

            raise NotImplementedError

        return cls(pre_upgrade=pre_upgrade, post_downgrade=post_downgrade)


def execute_replace_columns_enum_type(
    columns_by_table: dict[str, Collection[str]], enum_name: str, *enum_members: str
) -> None:
    """Changes the enum members for a single enum type for all columns using it.

    Steps:
    1. change old enum name to temp name
    2. create enum with new members and old name
    3. change column type from old enum (now with temp name) to new enum
    4. drop old enum
    """
    enum_name_tmp = f"{enum_name}_{get_random_hex_string()}"
    op.execute(format_rename_type(enum_name, enum_name_tmp))
    sa.Enum(*enum_members, name=enum_name).create(op.get_bind())

    for table_name, column_names in columns_by_table.items():
        for column_name in column_names:
            execute_alter_column_enum_type(table_name, column_name, enum_name)

    sa.Enum(name=enum_name_tmp).drop(op.get_bind())


def execute_remap_enum_members_or_delete_rows(
    table_name: str,
    column_name: str,
    enum_name: str,
    **new_and_old_member_pairs: Optional[str],
) -> None:
    """Looks up data containing specific enum values and either
    1. replaces all the values, if an old value is provided,
    or
    2. deletes the rows, if the old value is None.
    """
    # https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.execute

    enum_new = sa.Enum(*new_and_old_member_pairs.keys(), name=enum_name)
    table = sa.sql.table(table_name, sa.Column(column_name, enum_new, nullable=False))
    for new, old in new_and_old_member_pairs.items():
        if old:
            op.execute(
                table.update()
                .where(getattr(table.c, column_name) == op.inline_literal(new))
                .values(**{column_name: op.inline_literal(old)})
            )
        else:
            # TODO: add cascade delete
            op.execute(table.delete().where(getattr(table.c, column_name) == op.inline_literal(new)))


# TODO: implement cascade deletion
# def execute_delete_column_rows_with_enum_members(
#     table_name: str, column_name: str, enum_name: str, **new_and_old_member_pairs: tuple[str, str]
# ) -> None:
#     enum_new = sa.Enum(*new_and_old_member_pairs.values(), name=enum_name)
#     table = sa.sql.table(table_name, sa.Column(column_name, enum_new, nullable=False))
#     for new, old in new_and_old_member_pairs.items():
#         op.execute(table.delete().where(getattr(table.c, enum_name) == old))


def format_rename_type(old: str, new: str) -> str:
    return f"ALTER TYPE {old} RENAME TO {new}"


def format_drop_type(name: str) -> str:
    return f"DROP TYPE {name}"


def format_alter_column_type(table: str, column: str, type_: str) -> str:
    return f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_} USING {column}::text::{type_}"


def execute_alter_column_enum_type(table_name: str, column_name: str, enum_name: str) -> None:
    enum_ = sa.Enum(name=enum_name)
    op.alter_column(
        table_name=table_name,
        column_name=column_name,
        type_=enum_,
        postgresql_using=f"{column_name}::text::{enum_.name}",
    )


def get_random_hex_string(length: int = 8) -> str:
    return f"{random.getrandbits(4 * length):x}"


def enum_as_non_creatable_variant(name: str, *members: str) -> sa.Enum:
    enum_postgres = postgresql.ENUM(*members, name=name, create_type=False)

    return sa.Enum(*members, name=name).with_variant(enum_postgres, "postgresql")
